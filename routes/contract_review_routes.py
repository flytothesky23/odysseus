"""Owner-scoped REST surface for the native Contract Review workspace."""

from __future__ import annotations

import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.middleware import require_admin
from src.auth_helpers import require_user
from src.contract_review import (
    CONTRACT_REVIEW_SCHEMA,
    KORDOC_READ_ONLY_TOOLS,
    KOREAN_LAW_READ_ONLY_TOOLS,
    ContractReviewError,
    ContractReviewJobManager,
    ContractReviewWorkspaceService,
    KordocAdapter,
    KoreanLawAdapter,
    build_contract_review_markdown,
    contract_review_tool_policy,
    validate_contract_review_result,
)
from src.runtime_paths import get_app_root


def _bounded_timeout_from_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(value):
        return float(default)
    return max(0.05, min(value, 900.0))


def contract_review_timeouts_from_env() -> tuple[float, float]:
    """Return bounded adapter timeouts without weakening production defaults."""

    return (
        _bounded_timeout_from_env("ODYSSEUS_CONTRACT_REVIEW_KORDOC_TIMEOUT_SECONDS", 300.0),
        _bounded_timeout_from_env("ODYSSEUS_CONTRACT_REVIEW_LAW_TIMEOUT_SECONDS", 60.0),
    )


def _error_response(exc: ContractReviewError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": str(exc)},
    )


def _require_mapping(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ContractReviewError("invalid_request", "A JSON object is required.", 400)
    return payload


def _require_list(payload: Mapping[str, Any], name: str) -> list[Any]:
    value = payload.get(name) or []
    if not isinstance(value, list):
        raise ContractReviewError("invalid_request", f"{name} must be a list.", 400)
    return value


def _load_mcp_presets() -> dict[str, Any]:
    path = Path(get_app_root()) / "conf" / "contract_review_mcp_presets.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "kordoc": {"configurable": True, "allowed_tools": list(KORDOC_READ_ONLY_TOOLS)},
            "korean_law": {"configurable": True, "allowed_tools": list(KOREAN_LAW_READ_ONLY_TOOLS)},
        }
    return payload if isinstance(payload, dict) else {}


def _server_catalog(manager: Any, allowed_tools: tuple[str, ...]) -> list[dict[str, Any]]:
    """Return only non-secret, connected server/tool identifiers for the picker."""

    tools = manager.get_all_tools()
    if not isinstance(tools, list):
        raise TypeError("invalid MCP inventory")
    catalog: dict[str, dict[str, Any]] = {}
    for item in tools:
        if not isinstance(item, Mapping) or item.get("name") not in allowed_tools or item.get("is_disabled"):
            continue
        server_id = str(item.get("server_id") or "")
        if not server_id:
            continue
        entry = catalog.setdefault(server_id, {
            "id": server_id,
            "name": str(item.get("server_name") or server_id),
            "tools": [],
        })
        entry["tools"].append(str(item["name"]))
    for entry in catalog.values():
        entry["tools"] = sorted(set(entry["tools"]))
    return sorted(catalog.values(), key=lambda item: (item["name"].casefold(), item["id"]))


def _default_report_saver(*, owner: str, session_id: str, title: str, markdown: str) -> dict[str, Any]:
    """Persist a report only when the explicit report endpoint calls this."""

    from core.database import Document, DocumentVersion, Session, SessionLocal

    db = SessionLocal()
    try:
        session = db.query(Session).filter(Session.id == session_id).first()
        if session is None or (owner and session.owner != owner):
            raise ContractReviewError("session_not_found", "The requested session was not found.", 404)
        document_id = str(uuid.uuid4())
        document = Document(
            id=document_id,
            session_id=session_id,
            title=title,
            language="markdown",
            current_content=markdown,
            version_count=1,
            is_active=True,
            owner=owner or session.owner,
        )
        version = DocumentVersion(
            id=str(uuid.uuid4()),
            document_id=document_id,
            version_number=1,
            content=markdown,
            summary="Explicit Contract Review report save",
            source="user",
        )
        db.add(document)
        db.add(version)
        db.commit()
        return {"id": document_id, "title": title, "session_id": session_id}
    except ContractReviewError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise ContractReviewError("report_save_failed", "The report could not be saved.", 500) from exc
    finally:
        db.close()


def setup_contract_review_routes(
    service: ContractReviewWorkspaceService,
    mcp_manager: Any,
    *,
    law_mcp_manager: Any | None = None,
    report_saver: Callable[..., dict[str, Any]] | None = None,
    upload_handler: Any | None = None,
    kordoc_timeout: float = 300,
    law_timeout: float = 60,
) -> APIRouter:
    router = APIRouter(prefix="/api/contract-review", tags=["contract-review"])
    law_manager = law_mcp_manager or mcp_manager
    jobs = ContractReviewJobManager(
        KordocAdapter(mcp_manager, timeout=kordoc_timeout),
        KoreanLawAdapter(law_manager, timeout=law_timeout),
    )
    service.job_manager = jobs
    save_report = report_saver or _default_report_saver

    def owner_for(request: Request) -> str:
        return str(require_user(request) or "")

    @router.get("/profile")
    def profile(request: Request):
        owner_for(request)
        inventory_available = True
        try:
            kordoc_servers = _server_catalog(mcp_manager, KORDOC_READ_ONLY_TOOLS)
            law_servers = _server_catalog(law_manager, KOREAN_LAW_READ_ONLY_TOOLS)
        except Exception:
            inventory_available = False
            kordoc_servers = []
            law_servers = []
        policy = contract_review_tool_policy()
        return {
            "id": "contract_review",
            "name": "Contract Review",
            "mcp_runtime_id": jobs.runtime_id,
            "read_only": True,
            "generic_mcp_disabled": policy.disable_mcp,
            "inventory_available": inventory_available,
            "kordoc_servers": kordoc_servers,
            "korean_law_servers": law_servers,
            "disabled_tools": sorted(policy.disabled_tools),
            "mcp_presets": _load_mcp_presets(),
            "result_schema": CONTRACT_REVIEW_SCHEMA,
        }

    @router.post("/vault/index")
    async def index_vault(request: Request):
        try:
            owner = owner_for(request)
            require_admin(request)
            payload = _require_mapping(await request.json())
            return service.index_vault(
                owner,
                str(payload.get("workspace") or ""),
                str(payload.get("vault_path") or "."),
            )
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.post("/vault/search")
    async def search_vault(request: Request):
        try:
            owner = owner_for(request)
            payload = _require_mapping(await request.json())
            return service.search(
                owner,
                str(payload.get("snapshot_id") or ""),
                str(payload.get("vault_id") or ""),
                str(payload.get("query") or ""),
                include_body=bool(payload.get("include_body", False)),
                candidate_paths=payload.get("candidate_paths"),
                note_scope=payload.get("note_scope"),
                limit=int(payload.get("limit", 20)),
            )
        except (TypeError, ValueError):
            return _error_response(ContractReviewError("invalid_request", "Search options are invalid.", 400))
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.post("/vault/open")
    async def open_note(request: Request):
        try:
            owner = owner_for(request)
            payload = _require_mapping(await request.json())
            return service.open_note(
                owner,
                str(payload.get("snapshot_id") or ""),
                str(payload.get("vault_id") or ""),
                str(payload.get("path") or ""),
                payload.get("note_scope"),
            )
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.post("/context/prepare")
    async def prepare_context(request: Request):
        try:
            owner = owner_for(request)
            payload = _require_mapping(await request.json())
            selected = _require_list(payload, "selected_paths")
            kordoc_ids = _require_list(payload, "kordoc_job_ids")
            law_ids = _require_list(payload, "law_job_ids")
            if (kordoc_ids or law_ids) and payload.get("mcp_runtime_id") != jobs.runtime_id:
                raise ContractReviewError(
                    "stale_evidence_runtime",
                    "MCP evidence belongs to a previous app runtime. Re-run the evidence lookup.",
                    409,
                )
            local_evidence = jobs.completed_evidence(owner, kordoc_ids, kind="kordoc") if kordoc_ids else []
            law_evidence = jobs.completed_evidence(owner, law_ids, kind="law") if law_ids else []
            return service.build_turn_context(
                owner=owner,
                session_id=str(payload.get("session_id") or ""),
                snapshot_id=str(payload.get("snapshot_id") or ""),
                vault_id=str(payload.get("vault_id") or ""),
                selected_paths=selected,
                note_scope=payload.get("note_scope"),
                local_document_evidence=local_evidence,
                official_legal_evidence=law_evidence,
            )
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.post("/kordoc/jobs", status_code=202)
    async def start_kordoc(request: Request):
        try:
            owner = owner_for(request)
            require_admin(request)
            payload = _require_mapping(await request.json())
            arguments = _require_mapping(payload.get("arguments") or {})
            return jobs.start_kordoc(
                owner=owner,
                server_id=str(payload.get("server_id") or ""),
                tool=str(payload.get("tool") or ""),
                workspace=str(payload.get("workspace") or ""),
                relative_path=str(payload.get("file_path") or ""),
                arguments=arguments,
            )
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.post("/kordoc/upload-jobs", status_code=202)
    async def start_kordoc_upload(request: Request):
        try:
            owner = owner_for(request)
            if upload_handler is None or not hasattr(upload_handler, "resolve_upload"):
                raise ContractReviewError("upload_unavailable", "Document uploads are unavailable.", 503)
            payload = _require_mapping(await request.json())
            upload_id = str(payload.get("upload_id") or "")
            resolved = upload_handler.resolve_upload(upload_id, owner=owner)
            if not isinstance(resolved, Mapping) or not resolved.get("path"):
                raise ContractReviewError("upload_unavailable", "The uploaded document is unavailable.", 404)
            physical = Path(str(resolved["path"])).resolve()
            if not physical.is_file():
                raise ContractReviewError("upload_unavailable", "The uploaded document is unavailable.", 404)
            arguments = _require_mapping(payload.get("arguments") or {})
            return jobs.start_kordoc(
                owner=owner,
                server_id=str(payload.get("server_id") or ""),
                tool=str(payload.get("tool") or "parse_document"),
                workspace=str(physical.parent),
                relative_path=physical.name,
                arguments=arguments,
            )
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.post("/law/jobs", status_code=202)
    async def start_law(request: Request):
        try:
            owner = owner_for(request)
            payload = _require_mapping(await request.json())
            arguments = _require_mapping(payload.get("arguments") or {})
            return jobs.start_law(
                owner=owner,
                server_id=str(payload.get("server_id") or ""),
                tool=str(payload.get("tool") or ""),
                arguments=arguments,
            )
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str, request: Request):
        try:
            return jobs.get(owner_for(request), job_id)
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.delete("/jobs/{job_id}")
    async def cancel_job(job_id: str, request: Request):
        try:
            return await jobs.cancel(owner_for(request), job_id)
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.post("/results/validate")
    async def validate_result(request: Request):
        try:
            owner_for(request)
            return validate_contract_review_result(_require_mapping(await request.json()))
        except ContractReviewError as exc:
            return _error_response(exc)

    @router.post("/reports", status_code=201)
    async def create_report(request: Request):
        try:
            owner = owner_for(request)
            payload = _require_mapping(await request.json())
            title = str(payload.get("title") or "Contract Review").strip()[:200] or "Contract Review"
            result = validate_contract_review_result(_require_mapping(payload.get("result")))
            session_id = str(payload.get("session_id") or "")
            if not session_id or result.get("session_id") != session_id:
                raise ContractReviewError(
                    "result_session_mismatch",
                    "The validated result does not belong to the selected session.",
                    409,
                )
            markdown = build_contract_review_markdown(result)
            return save_report(
                owner=owner,
                session_id=session_id,
                title=title,
                markdown=markdown,
            )
        except ContractReviewError as exc:
            return _error_response(exc)

    return router
