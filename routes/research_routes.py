"""Research background task routes — /api/research/*."""

import asyncio
import json
import logging
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from core.middleware import INTERNAL_TOOL_USER
from src.endpoint_resolver import resolve_endpoint
from src.auth_helpers import _auth_disabled, get_current_user
from core.auth import RESERVED_USERNAMES
from src.constants import DEEP_RESEARCH_DIR
from src.research_handler import normalize_artifact_formats

_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9-]{1,128}$")

logger = logging.getLogger(__name__)

# Model-name substrings that are NOT chat/generation models — research must
# never pick these as its model. An OpenAI-style endpoint often lists
# `text-embedding-ada-002` etc. first in its model list, which is why research
# was failing with "Cannot reach model 'text-embedding-ada-002'".
_NON_CHAT_MODEL = (
    "text-embedding", "embedding", "tts-", "whisper", "dall-e",
    "moderation", "rerank", "reranker", "clip", "stable-diffusion",
)


def _first_chat_model(models) -> str:
    """First model that isn't an embedding/tts/etc. — falls back to models[0]."""
    for m in (models or []):
        if not any(p in str(m).lower() for p in _NON_CHAT_MODEL):
            return m
    return (models[0] if models else "")


def _resolve_research_endpoint(sess, owner: Optional[str] = None) -> tuple:
    """Return (endpoint_url, model, headers) for Deep Research, checking admin overrides."""
    owner = owner or getattr(sess, "owner", None) or None
    url, model, headers = resolve_endpoint(
        "research",
        fallback_url=sess.endpoint_url,
        fallback_model=sess.model,
        fallback_headers=sess.headers,
        owner=owner,
    )
    return url, model, headers


def _owned_enabled_endpoint(db, owner, endpoint_id=None):
    """An enabled ModelEndpoint VISIBLE to `owner` (their own rows + legacy
    null-owner "shared" rows), optionally narrowed to a specific endpoint_id;
    None if nothing visible matches.

    Owner-scoped on purpose. ModelEndpoint is per-user (core/database.py: non-null
    owner = private, "the model picker only shows the endpoint to that user") and
    holds a decrypted `api_key`. /api/research/start feeds the resolved row's
    api_key + base_url into research_handler.start_research(llm_endpoint=,
    llm_headers=), so an UNSCOPED lookup — by the caller-supplied endpoint_id, or
    via the bare first-enabled fallback — would let a research-privileged user
    spend ANOTHER user's API key/quota and reach whatever internal base_url they
    configured. Mirrors webhook_routes._first_enabled_endpoint and
    session_routes._owned_endpoint. A null/empty owner is a no-op (single-user /
    legacy mode).
    """
    from src.database import ModelEndpoint
    from src.auth_helpers import owner_filter
    q = db.query(ModelEndpoint).filter(ModelEndpoint.is_enabled == True)  # noqa: E712
    if endpoint_id:
        q = q.filter(ModelEndpoint.id == endpoint_id)
    return owner_filter(q, ModelEndpoint, owner).first()


def _resolve_endpoint_runtime(ep, owner=None, model: Optional[str] = None):
    """Resolve a ModelEndpoint row into (chat_url, model, headers).

    Mirrors endpoint_resolver.resolve_endpoint's provider-auth handling for
    panel-selected research endpoints. ChatGPT Subscription endpoints keep
    OAuth tokens in ProviderAuthSession, so ep.api_key is intentionally empty.
    """
    from src.endpoint_resolver import (
        build_chat_url,
        build_headers,
        resolve_endpoint_runtime as resolve_model_endpoint_runtime,
    )

    try:
        base, api_key = resolve_model_endpoint_runtime(ep, owner=owner)
    except Exception as e:
        logger.warning("Could not resolve endpoint credentials for research: %s", e)
        return None

    ep_model = (model or "").strip()
    if not ep_model:
        try:
            models = json.loads(ep.cached_models) if ep.cached_models else []
            if models:
                ep_model = _first_chat_model(models)
        except Exception:
            pass
    if not ep_model:
        return None
    return build_chat_url(base), ep_model, build_headers(api_key, base)


def setup_research_routes(research_handler, session_manager=None) -> APIRouter:
    router = APIRouter(tags=["research"])

    def _require_user(request: Request) -> str:
        """All research endpoints require an authenticated user. Research
        data isn't owner-scoped in the on-disk JSON yet, so we at least
        block anonymous access. Multi-tenant deploys should additionally
        verify the session belongs to this user."""
        user = get_current_user(request)
        if not user:
            if _auth_disabled():
                return ""
            raise HTTPException(401, "Not authenticated")
        return user

    def _require_admin_user(request: Request) -> str:
        user = _require_user(request)
        if _auth_disabled():
            return user
        auth_mgr = getattr(request.app.state, "auth_manager", None)
        if auth_mgr is not None and getattr(auth_mgr, "is_configured", False):
            try:
                if not auth_mgr.is_admin(user):
                    raise HTTPException(403, "Admin only")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(403, "Admin only")
        return user

    def _validate_session_id(session_id: str) -> None:
        if not _SESSION_ID_RE.fullmatch(session_id):
            raise HTTPException(400, "Invalid session ID format")

    def _owns_in_memory(session_id: str, user: str) -> bool:
        """Ownership check for an in-flight (in-memory) research task.
        Falls back to the on-disk JSON if the task has already finished."""
        entry = research_handler._active_tasks.get(session_id)
        if entry is not None:
            return entry.get("owner", "") == user
        # Task no longer in memory — check the persisted JSON.
        path = Path(DEEP_RESEARCH_DIR) / f"{session_id}.json"
        if not path.exists():
            return False
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("owner") == user
        except Exception:
            return False

    @router.get("/api/research/active")
    async def research_active(request: Request):
        """List all currently active (running) research tasks."""
        user = _require_user(request)
        active = []
        for sid, entry in research_handler._active_tasks.items():
            # SECURITY: only show this user's running tasks.
            if entry.get("owner", "") != user:
                continue
            if entry.get("status") == "running":
                active.append({
                    "session_id": sid,
                    "query": entry.get("query", ""),
                    "status": "running",
                    "progress": entry.get("progress", {}),
                    "started_at": entry.get("started_at", 0),
                    "artifact_formats": normalize_artifact_formats(entry.get("artifact_formats")),
                    "reasoning_effort": entry.get("reasoning_effort"),
                })
        return {"active": active}

    @router.get("/api/research/status/{session_id}")
    async def research_status(session_id: str, request: Request):
        user = _require_user(request)
        _validate_session_id(session_id)
        if not _owns_in_memory(session_id, user):
            raise HTTPException(404, "No research found for this session")
        status = research_handler.get_status(session_id)
        if status is None:
            raise HTTPException(404, "No research found for this session")
        return status

    @router.post("/api/research/cancel/{session_id}")
    async def research_cancel(session_id: str, request: Request):
        user = _require_user(request)
        _validate_session_id(session_id)
        if not _owns_in_memory(session_id, user):
            raise HTTPException(404, "No research found for this session")
        cancelled = research_handler.cancel_research(session_id)
        return {"cancelled": cancelled}

    @router.post("/api/research/result/{session_id}")
    async def research_result(session_id: str, request: Request):
        user = _require_user(request)
        _validate_session_id(session_id)
        if not _owns_in_memory(session_id, user):
            raise HTTPException(404, "No research result available")
        result = research_handler.get_result(session_id)
        if result is None:
            raise HTTPException(404, "No research result available")
        sources = research_handler.get_sources(session_id) or []
        raw_findings = research_handler.get_raw_findings(session_id) or []
        research_handler.clear_result(session_id)
        return {"result": result, "sources": sources, "raw_findings": raw_findings}

    def _assert_owns_research(session_id: str, user: str) -> None:
        """404-not-403 ownership gate for a research session's on-disk JSON.
        Use BEFORE returning any data or mutating the file."""
        path = Path(DEEP_RESEARCH_DIR) / f"{session_id}.json"
        if not path.exists():
            raise HTTPException(404, "Research not found")
        try:
            owner = json.loads(path.read_text(encoding="utf-8")).get("owner")
        except Exception:
            raise HTTPException(404, "Research not found")
        if owner != user:
            raise HTTPException(404, "Research not found")

    def _download_headers(session_id: str, suffix: str, download: bool) -> dict:
        if not download:
            return {}
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "-", session_id)
        return {"Content-Disposition": f'attachment; filename="odysseus-research-{safe}{suffix}"'}

    @router.get("/api/research/report/{session_id}")
    async def research_report(session_id: str, request: Request):
        """Serve the visual HTML report for a completed research session."""
        user = _require_user(request)
        _validate_session_id(session_id)
        _assert_owns_research(session_id, user)
        logger.info(f"Visual report requested for session {session_id}")
        try:
            html_content = research_handler.get_report_html(session_id)
        except Exception as e:
            logger.error(f"Visual report generation error: {e}", exc_info=True)
            raise HTTPException(500, f"Report generation failed: {e}")
        if html_content is None:
            logger.warning(f"No report data found for session {session_id}")
            raise HTTPException(404, "No visual report available for this session")
        return HTMLResponse(content=html_content)

    @router.get("/api/research/report/{session_id}/markdown")
    async def research_report_markdown(
        session_id: str,
        request: Request,
        download: bool = Query(False),
    ):
        """Serve an Obsidian-friendly Markdown export for a completed research session."""
        user = _require_user(request)
        _validate_session_id(session_id)
        _assert_owns_research(session_id, user)
        try:
            markdown = research_handler.get_report_markdown(session_id)
        except Exception as e:
            logger.error(f"Markdown report generation error: {e}", exc_info=True)
            raise HTTPException(500, f"Markdown report generation failed: {e}")
        if markdown is None:
            raise HTTPException(404, "No markdown report available for this session")
        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers=_download_headers(session_id, ".md", download),
        )

    @router.get("/api/research/report/{session_id}/session.json")
    async def research_report_session_json(
        session_id: str,
        request: Request,
        download: bool = Query(False),
    ):
        """Serve a structured JSON export for a completed research session."""
        user = _require_user(request)
        _validate_session_id(session_id)
        _assert_owns_research(session_id, user)
        try:
            data = research_handler.get_report_session_export(session_id)
        except Exception as e:
            logger.error(f"Research session JSON export error: {e}", exc_info=True)
            raise HTTPException(500, f"Session JSON export failed: {e}")
        if data is None:
            raise HTTPException(404, "No session JSON available for this session")
        return JSONResponse(
            content=data,
            headers=_download_headers(session_id, ".odysseus-session.json", download),
        )

    class HideImageRequest(BaseModel):
        url: str

    @router.post("/api/research/{session_id}/hide-image")
    async def research_hide_image(session_id: str, body: HideImageRequest, request: Request):
        """Mark an image URL as hidden for this research's visual report.
        Persisted to the research JSON so subsequent /report renders skip it."""
        user = _require_user(request)
        _validate_session_id(session_id)
        _assert_owns_research(session_id, user)
        ok = research_handler.hide_image(session_id, body.url)
        if not ok:
            raise HTTPException(404, "Research not found")
        return {"ok": True}

    @router.post("/api/research/{session_id}/unhide-images")
    async def research_unhide_images(session_id: str, request: Request):
        """Clear the hidden-images list for a research session."""
        user = _require_user(request)
        _validate_session_id(session_id)
        _assert_owns_research(session_id, user)
        ok = research_handler.unhide_all_images(session_id)
        if not ok:
            raise HTTPException(404, "Research not found")
        return {"ok": True}

    @router.get("/api/research/library")
    async def research_library(
        request: Request,
        search: Optional[str] = Query(None),
        sort: str = Query("recent"),
        limit: int = Query(50),
        archived: bool = Query(False),
    ):
        user = _require_user(request)
        """List all completed research for the Library panel."""
        data_dir = Path(DEEP_RESEARCH_DIR)
        items = []
        for p in data_dir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                # SECURITY: only show research belonging to this user. Legacy
                # JSONs without an `owner` field are hidden — auth was the only
                # gate before, so every user saw every other user's reports.
                if d.get("owner") != user:
                    continue
                # Archived view shows ONLY archived reports; default hides them.
                if bool(d.get("archived")) != archived:
                    continue
                query = d.get("query", "")
                if search and search.lower() not in query.lower():
                    continue
                sources = d.get("sources", [])
                items.append({
                    "id": p.stem,
                    "query": query,
                    "category": d.get("category") or "",
                    "source_count": len(sources),
                    "status": d.get("status", "done"),
                    "duration": d.get("stats", {}).get("Duration", ""),
                    "rounds": d.get("stats", {}).get("Rounds", ""),
                    "artifact_formats": normalize_artifact_formats(d.get("artifact_formats")),
                    "reasoning_effort": d.get("reasoning_effort") or "",
                    "started_at": d.get("started_at", 0),
                    "completed_at": d.get("completed_at", 0),
                    "archived": bool(d.get("archived")),
                })
            except Exception:
                continue

        # Sort
        if sort == "recent":
            items.sort(key=lambda x: x["completed_at"] or 0, reverse=True)
        elif sort == "oldest":
            items.sort(key=lambda x: x["completed_at"] or 0)
        elif sort == "most-messages":
            items.sort(key=lambda x: x["source_count"], reverse=True)
        elif sort == "alpha":
            items.sort(key=lambda x: x["query"].lower())

        return {"research": items[:limit], "total": len(items)}

    @router.get("/api/research/detail/{session_id}")
    async def research_detail(session_id: str, request: Request):
        """Return the full JSON for a single research result — sources,
        summary, stats — used by the Library preview panel."""
        user = _require_user(request)
        _validate_session_id(session_id)
        path = Path(DEEP_RESEARCH_DIR) / f"{session_id}.json"
        if not path.exists():
            raise HTTPException(404, "Research not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise HTTPException(500, f"Failed to read research: {e}")
        # SECURITY: 404 (not 403) so we don't leak that the report exists.
        if data.get("owner") != user:
            raise HTTPException(404, "Research not found")
        return data

    @router.post("/api/research/{session_id}/archive")
    async def research_archive(session_id: str, request: Request, archived: bool = Query(True)):
        """Soft-archive / restore a research report (sets `archived` in its JSON)."""
        user = _require_user(request)
        _validate_session_id(session_id)
        path = Path(DEEP_RESEARCH_DIR) / f"{session_id}.json"
        if not path.exists():
            raise HTTPException(404, "Research not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("owner") != user:
                raise HTTPException(404, "Research not found")
            data["archived"] = bool(archived)
            path.write_text(json.dumps(data), encoding="utf-8")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"Failed to update research: {e}")
        return {"ok": True, "id": session_id, "archived": bool(archived)}

    @router.delete("/api/research/{session_id}")
    async def research_delete(session_id: str, request: Request):
        """Delete a research result from disk."""
        user = _require_user(request)
        _validate_session_id(session_id)
        data_dir = Path(DEEP_RESEARCH_DIR)
        json_path = data_dir / f"{session_id}.json"
        deleted = False
        if json_path.exists():
            # SECURITY: verify ownership before letting the caller delete it.
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                if data.get("owner") != user:
                    raise HTTPException(404, "Research not found")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(404, "Research not found")
            json_path.unlink()
            deleted = True
        return {"deleted": deleted}

    @router.get("/api/research/knowledge/settings")
    async def research_knowledge_settings(request: Request):
        """Return configured Obsidian knowledge-base status for the research UI."""
        _require_user(request)
        from src.knowledge_base import configured_local_roots, configured_vault_root
        from src.settings import get_setting

        root = configured_vault_root()
        local_roots = configured_local_roots()
        source_mode = str(get_setting("research_source_mode", "web") or "web").strip() or "web"
        return {
            "configured": root is not None or bool(local_roots),
            "root": str(root) if root else "",
            "local_roots": local_roots,
            "source_mode": source_mode,
            "max_chunks": int(get_setting("research_knowledge_max_chunks", 12) or 12),
            "auto_index": bool(get_setting("research_knowledge_auto_index", True)),
        }

    @router.get("/api/research/knowledge/folders")
    async def research_knowledge_folders(
        request: Request,
        parent: str = Query(""),
        recursive: bool = Query(True),
        max_depth: int = Query(3, ge=1, le=6),
    ):
        """List selectable folders under configured Obsidian/local knowledge roots."""
        _require_user(request)
        from src.knowledge_base import KnowledgeBaseError, list_knowledge_folders

        try:
            return list_knowledge_folders(parent, recursive=recursive, max_depth=max_depth)
        except KnowledgeBaseError as e:
            raise HTTPException(400, str(e))

    class KnowledgeLocalFolderRequest(BaseModel):
        path: str
        label: Optional[str] = None

    @router.post("/api/research/knowledge/local-folders")
    async def research_add_local_knowledge_folder(body: KnowledgeLocalFolderRequest, request: Request):
        """Persist a local folder as a selectable Deep Research knowledge source."""
        _require_admin_user(request)
        from src.knowledge_base import KnowledgeBaseError, add_local_knowledge_root

        try:
            folder = add_local_knowledge_root(body.path, label=body.label or "")
            return {"ok": True, "folder": folder}
        except KnowledgeBaseError as e:
            raise HTTPException(400, str(e))

    @router.delete("/api/research/knowledge/local-folders/{root_id}")
    async def research_remove_local_knowledge_folder(root_id: str, request: Request):
        """Remove a previously added local knowledge folder."""
        _require_admin_user(request)
        from src.knowledge_base import remove_local_knowledge_root

        if not re.fullmatch(r"[a-zA-Z0-9_-]{6,64}", root_id or ""):
            raise HTTPException(400, "Invalid local folder id")
        removed = remove_local_knowledge_root(root_id)
        if not removed:
            raise HTTPException(404, "Local knowledge folder not found")
        return {"ok": True, "removed": True}

    @router.post("/api/research/knowledge/local-folders/pick")
    async def research_pick_local_knowledge_folder(request: Request):
        """Open the macOS folder picker and add the selected folder."""
        _require_admin_user(request)
        if sys.platform != "darwin":
            raise HTTPException(400, "Folder picker is only available on macOS.")
        from src.knowledge_base import KnowledgeBaseError, add_local_knowledge_root

        script = 'POSIX path of (choose folder with prompt "Odysseus Deep Research 지식 소스로 사용할 폴더를 선택하세요")'
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(408, "Folder picker timed out")
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            if "User canceled" in stderr or "사용자가 취소" in stderr:
                return {"ok": False, "cancelled": True}
            raise HTTPException(400, stderr or "Folder picker was cancelled")
        selected = (proc.stdout or "").strip()
        try:
            folder = add_local_knowledge_root(selected)
            return {"ok": True, "folder": folder}
        except KnowledgeBaseError as e:
            raise HTTPException(400, str(e))

    # ------------------------------------------------------------------
    # Panel endpoints — launch research without a chat session
    # ------------------------------------------------------------------

    class ResearchStartRequest(BaseModel):
        query: str
        # max_rounds=0 means "Auto" — let the AI decide when to stop, capped at 20.
        max_rounds: int = Field(default=0, ge=0, le=20)
        search_provider: Optional[str] = None
        endpoint_id: Optional[str] = None
        model: Optional[str] = None
        max_time: int = Field(default=300, ge=60, le=1800)
        extraction_timeout: Optional[int] = Field(default=None, ge=15, le=3600)
        extraction_concurrency: Optional[int] = Field(default=None, ge=1, le=12)
        category: Optional[str] = None
        source_mode: Optional[str] = None
        knowledge_folders: List[str] = Field(default_factory=list)
        artifact_formats: List[str] = Field(default_factory=lambda: ["html"])
        reasoning_effort: Optional[str] = None

    @router.post("/api/research/start")
    async def research_start(body: ResearchStartRequest, request: Request):
        """Launch a research job from the dedicated panel."""
        from src.auth_helpers import require_privilege
        from src.knowledge_base import (
            KnowledgeBaseError,
            knowledge_folders_for_source_mode,
            normalize_source_mode,
        )
        from src.settings import get_setting
        from src.llm_core import _normalize_reasoning_effort
        user = require_privilege(request, "can_use_research")
        if user == INTERNAL_TOOL_USER:
            tool_owner = (request.headers.get("X-Odysseus-Owner") or "").strip()
            if tool_owner and tool_owner not in RESERVED_USERNAMES:
                auth_mgr = getattr(request.app.state, "auth_manager", None)
                if auth_mgr is not None and getattr(auth_mgr, "is_configured", False):
                    try:
                        privs = auth_mgr.get_privileges(tool_owner) or {}
                        if not privs.get("can_use_research", True):
                            raise HTTPException(403, f"Your account is not allowed to can use research.")
                    except HTTPException:
                        raise
                    except Exception:
                        pass
                user = tool_owner
        session_id = f"rp-{uuid.uuid4().hex[:12]}"

        if body.endpoint_id:
            from src.database import SessionLocal
            db = SessionLocal()
            try:
                # Owner-scoped: never resolve another user's private endpoint
                # (and its decrypted api_key / internal base_url). A scoped miss
                # reads as 404 so the endpoint's existence isn't revealed.
                ep = _owned_enabled_endpoint(db, user, body.endpoint_id)
                if not ep:
                    raise HTTPException(404, "Endpoint not found or disabled")
                resolved = _resolve_endpoint_runtime(ep, owner=user, model=body.model)
                if not resolved:
                    raise HTTPException(400, "Endpoint is not configured with a usable model.")
                ep_url, ep_model, ep_headers = resolved
            finally:
                db.close()
        else:
            ep_url, ep_model, ep_headers = resolve_endpoint("research", owner=user)
            if not ep_url:
                ep_url, ep_model, ep_headers = resolve_endpoint("utility", owner=user)
            # When neither research nor utility is configured, use the user's
            # configured DEFAULT model (default_endpoint_id/default_model) rather
            # than arbitrarily grabbing the first enabled endpoint's first model
            # (which surfaced gpt-3.5). "Default" should mean the default model.
            if not ep_url:
                ep_url, ep_model, ep_headers = resolve_endpoint("default", owner=user)
            if not ep_url:
                ep_url, ep_model, ep_headers = resolve_endpoint("chat", owner=user)
            if not ep_url:
                from src.database import SessionLocal
                db = SessionLocal()
                try:
                    # Owner-scoped first-enabled fallback: the caller's own rows
                    # + legacy null-owner shared rows only — never borrow another
                    # user's private endpoint/api_key. Same fix as the
                    # /api/v1/chat fallback (webhook_routes._first_enabled_endpoint).
                    ep = _owned_enabled_endpoint(db, user)
                    if ep:
                        resolved = _resolve_endpoint_runtime(ep, owner=user)
                        if resolved:
                            ep_url, ep_model, ep_headers = resolved
                finally:
                    db.close()
            if not ep_url:
                raise HTTPException(400, "No endpoints configured. Add one in Settings first.")
            if body.model:
                ep_model = body.model

        requested_source_mode = body.source_mode or get_setting("research_source_mode", "web")
        try:
            resolved_knowledge_folders = knowledge_folders_for_source_mode(
                requested_source_mode,
                body.knowledge_folders,
            )
        except KnowledgeBaseError as e:
            raise HTTPException(400, str(e))
        artifact_formats = normalize_artifact_formats(body.artifact_formats)
        reasoning_effort = _normalize_reasoning_effort(body.reasoning_effort)

        # max_rounds=0 → "Auto", let AI decide; pass 20 as the safety cap.
        effective_max_rounds = body.max_rounds if body.max_rounds > 0 else 20
        research_handler.start_research(
            session_id=session_id,
            query=body.query,
            llm_endpoint=ep_url,
            llm_model=ep_model,
            max_time=body.max_time,
            llm_headers=ep_headers,
            max_rounds=effective_max_rounds,
            search_provider=body.search_provider or None,
            category=body.category or None,
            source_mode=normalize_source_mode(requested_source_mode),
            knowledge_folders=resolved_knowledge_folders,
            extraction_timeout=body.extraction_timeout,
            extraction_concurrency=body.extraction_concurrency,
            artifact_formats=artifact_formats,
            reasoning_effort=reasoning_effort,
            owner=user,
        )
        return {
            "session_id": session_id,
            "status": "running",
            "query": body.query,
            "artifact_formats": artifact_formats,
            "reasoning_effort": reasoning_effort,
        }

    @router.get("/api/research/stream/{session_id}")
    async def research_stream(session_id: str, request: Request):
        """SSE stream of research progress events."""
        user = _require_user(request)
        _validate_session_id(session_id)
        if not _owns_in_memory(session_id, user):
            raise HTTPException(404, "No research found for this session")
        async def _generate():
            last_progress = None
            while True:
                status = research_handler.get_status(session_id)
                if status is None:
                    yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                    return
                st = status.get("status", "")
                progress = status.get("progress", {})
                if progress != last_progress:
                    last_progress = progress
                    yield f"data: {json.dumps({**progress, 'status': st})}\n\n"
                if st != "running":
                    final = {'status': st, 'final': True}
                    task = research_handler._active_tasks.get(session_id, {})
                    if st == "error" and task.get("result"):
                        final['error'] = str(task["result"])[:500]
                    yield f"data: {json.dumps(final)}\n\n"
                    return
                await asyncio.sleep(1.5)

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/api/research/result-peek/{session_id}")
    async def research_result_peek(session_id: str, request: Request):
        """Get research result without clearing it (for panel use)."""
        user = _require_user(request)
        _validate_session_id(session_id)
        if not _owns_in_memory(session_id, user):
            raise HTTPException(404, "No research found for this session")
        result = research_handler.get_result(session_id)
        if result is None:
            p = Path(DEEP_RESEARCH_DIR) / f"{session_id}.json"
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                return {
                    "result": d.get("result", ""),
                    "sources": d.get("sources", []),
                    "raw_findings": d.get("raw_findings", []),
                    "category": d.get("category") or "",
                    "artifact_formats": normalize_artifact_formats(d.get("artifact_formats")),
                    "reasoning_effort": d.get("reasoning_effort") or "",
                }
            raise HTTPException(404, "No research result available")
        sources = research_handler.get_sources(session_id) or []
        raw_findings = research_handler.get_raw_findings(session_id) or []
        task = research_handler._active_tasks.get(session_id, {})
        return {
            "result": result,
            "sources": sources,
            "raw_findings": raw_findings,
            "category": "",
            "artifact_formats": normalize_artifact_formats(task.get("artifact_formats")),
            "reasoning_effort": task.get("reasoning_effort") or "",
        }

    @router.post("/api/research/spinoff/{session_id}")
    async def research_spinoff(session_id: str, request: Request):
        """Create a new chat session pre-seeded with this research as context.

        Reads the persisted research result + sources for `session_id`, creates
        a fresh session (inheriting endpoint/model/headers from the source
        session if available, otherwise from the resolved chat endpoint), and
        injects a single system message containing the report and sources so
        the user can ask follow-up questions in a clean conversation.
        """
        user = _require_user(request)
        _validate_session_id(session_id)
        # SECURITY: gate on ownership before reading the persisted research —
        # otherwise any authenticated user could spin off (and thereby read)
        # another user's report by guessing its session ID. Mirrors every other
        # endpoint in this file (see result_peek above).
        if not _owns_in_memory(session_id, user):
            raise HTTPException(404, "No research found for this session")
        if session_manager is None:
            raise HTTPException(500, "session_manager not configured")

        # Load research data — prefer in-memory result, fall back to disk
        result = research_handler.get_result(session_id)
        sources = research_handler.get_sources(session_id) or []
        query = ""

        path = Path(DEEP_RESEARCH_DIR) / f"{session_id}.json"
        if path.exists():
            try:
                disk = json.loads(path.read_text(encoding="utf-8"))
                if not result:
                    result = disk.get("result")
                if not sources:
                    sources = disk.get("sources", []) or []
                query = disk.get("query", "") or ""
            except Exception as e:
                logger.warning(f"Could not read research JSON for spinoff: {e}")

        if not result:
            raise HTTPException(404, "No research result available for this session")

        # Inherit endpoint/model/headers from the source session when possible.
        # For panel-launched research (rp-* IDs), there is no chat session, so
        # fall back through the same chain as /api/research/start: research →
        # utility → first enabled endpoint in the DB.
        ep_url, ep_model, ep_headers = "", "", {}
        try:
            src_sess = session_manager.get_session(session_id)
            ep_url = src_sess.endpoint_url or ""
            ep_model = src_sess.model or ""
            ep_headers = dict(src_sess.headers or {})
        except KeyError:
            pass

        def _merge(r_url, r_model, r_headers):
            nonlocal ep_url, ep_model, ep_headers
            if not ep_url and r_url:
                ep_url = r_url
            if not ep_model and r_model:
                ep_model = r_model
            if not ep_headers and r_headers:
                ep_headers = dict(r_headers)

        if not ep_url or not ep_model:
            _merge(*resolve_endpoint("chat", owner=user))
        if not ep_url or not ep_model:
            _merge(*resolve_endpoint("research", owner=user))
        if not ep_url or not ep_model:
            _merge(*resolve_endpoint("utility", owner=user))
        if not ep_url or not ep_model:
            # Last resort: this user's enabled endpoint, plus legacy shared rows.
            from src.database import SessionLocal
            from src.endpoint_resolver import normalize_base, build_chat_url, build_headers
            db = SessionLocal()
            try:
                ep = _owned_enabled_endpoint(db, user)
                if ep:
                    base = normalize_base(ep.base_url)
                    fallback_url = build_chat_url(base)
                    fallback_headers = build_headers(ep.api_key, base)
                    fallback_model = ""
                    if ep.cached_models:
                        try:
                            models = json.loads(ep.cached_models)
                            if models:
                                fallback_model = _first_chat_model(models)
                        except Exception:
                            pass
                    _merge(fallback_url, fallback_model, fallback_headers)
            finally:
                db.close()

        if not ep_url or not ep_model:
            raise HTTPException(400, "No endpoint configured — add one in Settings first")

        # Create new session
        new_sid = str(uuid.uuid4())

        title_query = (query or "research").strip()
        if len(title_query) > 60:
            title_query = title_query[:57] + "…"
        new_name = f"Follow-up: {title_query}"

        new_sess = session_manager.create_session(
            session_id=new_sid,
            name=new_name,
            endpoint_url=ep_url,
            model=ep_model,
            rag=False,
            owner=user,
        )
        if ep_headers:
            new_sess.headers = ep_headers
            session_manager.save_sessions()
        try:
            from src.event_bus import fire_event
            fire_event("session_created", user)
        except Exception:
            logger.debug("session_created event dispatch failed", exc_info=True)

        # Build the priming system message — report only, no sources injected.
        # The user can open the visual report for source details; keeping sources
        # out of the chat context saves tokens and avoids the AI fabricating
        # citations.
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        primer = (
            f"[Research context — {date_str}]\n\n"
            f"The user previously ran a deep research investigation. Use the "
            f"report below as your primary knowledge base when answering "
            f"follow-up questions. If the user asks something not covered, "
            f"say so plainly rather than guessing.\n\n"
            f"=== ORIGINAL QUERY ===\n{query or '(not recorded)'}\n\n"
            f"=== REPORT ===\n{result}"
        )

        from core.models import ChatMessage
        new_sess.add_message(ChatMessage(
            role="system",
            content=primer,
            metadata={"research_spinoff_from": session_id},
        ))
        session_manager.save_sessions()

        return {
            "session_id": new_sid,
            "name": new_name,
            "source_count": len(sources),
        }

    return router
