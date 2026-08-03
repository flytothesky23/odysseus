import asyncio
import re
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request

from routes.contract_review_routes import contract_review_timeouts_from_env, setup_contract_review_routes
from src.contract_review import ContractReviewWorkspaceService

from tests.test_contract_review_workspace_v2 import FakeMcpManager, _valid_result


@pytest.fixture
def contract_api(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    workspace = tmp_path / "workspace"
    vault = workspace / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Agreement.md").write_text(
        "---\ntitle: 기본 계약\naliases: [MSA]\n---\n대금 지급 근거",
        encoding="utf-8",
    )
    (vault / "archive").mkdir()
    (vault / "archive" / "Hidden.md").write_text("제외된 지급 근거", encoding="utf-8")
    document = workspace / "documents" / "agreement.pdf"
    document.parent.mkdir()
    document.write_bytes(b"fixture")
    saved = []

    class UploadHandler:
        def resolve_upload(self, upload_id, owner=None, **_kwargs):
            if upload_id != "upload-1" or owner != "alice":
                return None
            return {"id": upload_id, "name": "agreement.pdf", "path": str(document)}

    def save_report(*, owner, session_id, title, markdown):
        saved.append((owner, session_id, title, markdown))
        return {"id": "report-1", "title": title, "session_id": session_id}

    app = FastAPI()
    app.state.auth_manager = SimpleNamespace(
        is_configured=True,
        is_admin=lambda user: user in {"alice", "bob"},
    )

    @app.middleware("http")
    async def identify(request: Request, call_next):
        request.state.current_user = request.headers.get("x-test-user")
        return await call_next(request)

    app.include_router(setup_contract_review_routes(
        ContractReviewWorkspaceService(max_body_candidates=1),
        FakeMcpManager(),
        law_mcp_manager=FakeMcpManager(kind="korean-law"),
        report_saver=save_report,
        upload_handler=UploadHandler(),
        kordoc_timeout=1,
        law_timeout=1,
    ))
    return app, workspace, saved


@pytest.mark.asyncio
async def test_note_document_upload_job_is_owner_scoped_and_uses_the_verified_upload_path(contract_api):
    app, _workspace, _saved = contract_api
    started = await _request(app, "POST", "/api/contract-review/kordoc/upload-jobs", json={
        "upload_id": "upload-1", "server_id": "kordoc",
        "tool": "parse_document", "arguments": {"ocr": False},
    })
    assert started.status_code == 202
    job_id = started.json()["id"]
    for _ in range(30):
        state = await _request(app, "GET", f"/api/contract-review/jobs/{job_id}")
        if state.json()["state"] not in {"admitted", "running", "cancelling"}:
            break
        await asyncio.sleep(0.01)
    assert state.json()["state"] == "completed"
    assert state.json()["result"]["document"].endswith(".pdf")

    crossed = await _request(app, "POST", "/api/contract-review/kordoc/upload-jobs", owner="bob", json={
        "upload_id": "upload-1", "server_id": "kordoc",
        "tool": "parse_document", "arguments": {},
    })
    assert crossed.status_code == 404
    assert "agreement.pdf" not in crossed.text


async def _request(app, method, path, *, owner="alice", **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    if owner is not None:
        headers["x-test-user"] = owner
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, headers=headers, **kwargs)


@pytest.mark.asyncio
async def test_search_parse_law_context_and_explicit_save(contract_api):
    app, workspace, saved = contract_api
    profile = await _request(app, "GET", "/api/contract-review/profile")
    assert profile.status_code == 200
    assert profile.json()["result_schema"] == "contract-review.v2"
    assert re.fullmatch(r"[a-f0-9]{32}", profile.json()["mcp_runtime_id"])
    assert profile.json()["generic_mcp_disabled"] is True
    assert profile.json()["kordoc_servers"] == [{
        "id": "kordoc", "name": "kordoc", "tools": ["parse_document"],
    }]
    assert profile.json()["korean_law_servers"] == [{
        "id": "korean-law", "name": "korean-law", "tools": [
            "get_decision_text", "get_law_text", "search_decisions", "search_law",
        ],
    }]

    index_response = await _request(app, "POST", "/api/contract-review/vault/index", json={
        "workspace": str(workspace), "vault_path": "vault",
    })
    assert index_response.status_code == 200
    indexed = index_response.json()
    assert saved == []

    metadata = await _request(app, "POST", "/api/contract-review/vault/search", json={
        "snapshot_id": indexed["snapshot_id"], "vault_id": indexed["vault_id"],
        "query": "MSA", "include_body": False,
    })
    assert metadata.status_code == 200
    assert metadata.json()["body_read_count"] == 0
    assert saved == []

    parsed = await _request(app, "POST", "/api/contract-review/kordoc/jobs", json={
        "server_id": "kordoc", "tool": "parse_document", "workspace": str(workspace),
        "file_path": "documents/agreement.pdf", "arguments": {},
    })
    assert parsed.status_code == 202
    parser_id = parsed.json()["id"]
    assert parsed.json()["mcp_runtime_id"] == profile.json()["mcp_runtime_id"]
    for _ in range(30):
        parser = await _request(app, "GET", f"/api/contract-review/jobs/{parser_id}")
        if parser.json()["state"] not in {"admitted", "running", "cancelling"}:
            break
        await asyncio.sleep(0.01)
    assert parser.json()["state"] == "completed"

    law = await _request(app, "POST", "/api/contract-review/law/jobs", json={
        "server_id": "korean-law", "tool": "search_law",
        "arguments": {"query": "대한민국헌법", "display": 1},
    })
    assert law.status_code == 202
    law_id = law.json()["id"]
    assert law.json()["mcp_runtime_id"] == profile.json()["mcp_runtime_id"]
    for _ in range(30):
        law_state = await _request(app, "GET", f"/api/contract-review/jobs/{law_id}")
        if law_state.json()["state"] not in {"admitted", "running", "cancelling"}:
            break
        await asyncio.sleep(0.01)
    assert law_state.json()["state"] == "completed"

    prepared = await _request(app, "POST", "/api/contract-review/context/prepare", json={
        "session_id": "session-1", "snapshot_id": indexed["snapshot_id"],
        "vault_id": indexed["vault_id"], "selected_paths": ["Agreement.md"],
        "kordoc_job_ids": [parser_id], "law_job_ids": [law_id],
        "mcp_runtime_id": profile.json()["mcp_runtime_id"],
    })
    assert prepared.status_code == 200
    payload = prepared.json()
    assert payload["strategy"] == "fresh"
    assert payload["local_document_evidence"]
    assert payload["official_legal_evidence"]
    assert payload["official_legal_evidence"][0]["citation_id"] == "law.go.kr · 대한민국헌법 · MST 61603"
    assert payload["official_legal_evidence"][0]["tool"] == "get_law_text"
    assert str(workspace) not in prepared.text
    assert saved == []

    followed_up = await _request(app, "POST", "/api/contract-review/context/prepare", json={
        "session_id": "session-1", "snapshot_id": indexed["snapshot_id"],
        "vault_id": indexed["vault_id"], "selected_paths": ["Agreement.md"],
        "kordoc_job_ids": [parser_id], "law_job_ids": [law_id],
        "mcp_runtime_id": profile.json()["mcp_runtime_id"],
    })
    assert followed_up.status_code == 200
    assert followed_up.json()["strategy"] == "reuse"
    assert followed_up.json()["evidence_fingerprint"] == payload["evidence_fingerprint"]

    result = _valid_result()
    result["evidence_fingerprint"] = payload["evidence_fingerprint"]
    validated = await _request(app, "POST", "/api/contract-review/results/validate", json=result)
    assert validated.status_code == 200
    assert saved == []

    validated_result = validated.json()
    report = await _request(app, "POST", "/api/contract-review/reports", json={
        "session_id": "session-1", "title": "Contract Review", "result": validated_result,
    })
    assert report.status_code == 201
    assert report.json()["id"] == "report-1"
    assert len(saved) == 1
    assert saved[0][0] == "alice"

    mismatched = await _request(app, "POST", "/api/contract-review/reports", json={
        "session_id": "another-session", "title": "Contract Review", "result": validated_result,
    })
    assert mismatched.status_code == 409
    assert mismatched.json()["error"] == "result_session_mismatch"
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_route_owner_isolation_and_unauthenticated_rejection(contract_api):
    app, workspace, _saved = contract_api
    indexed = (await _request(app, "POST", "/api/contract-review/vault/index", json={
        "workspace": str(workspace), "vault_path": "vault",
    })).json()

    crossed = await _request(app, "POST", "/api/contract-review/vault/search", owner="bob", json={
        "snapshot_id": indexed["snapshot_id"], "vault_id": indexed["vault_id"], "query": "MSA",
    })
    assert crossed.status_code in {403, 404}
    assert str(workspace) not in crossed.text

    anonymous = await _request(app, "GET", "/api/contract-review/profile", owner=None)
    assert anonymous.status_code == 401


@pytest.mark.asyncio
async def test_vault_markdown_route_writes_only_after_explicit_owner_scoped_request(contract_api):
    app, workspace, _saved = contract_api
    vault = workspace / "vault"
    indexed = (await _request(app, "POST", "/api/contract-review/vault/index", json={
        "workspace": str(workspace), "vault_path": "vault",
    })).json()
    target = vault / "archive" / "AI 검토 결과.md"
    assert not target.exists()

    crossed = await _request(app, "POST", "/api/contract-review/vault/notes", owner="bob", json={
        "snapshot_id": indexed["snapshot_id"], "vault_id": indexed["vault_id"],
        "folder": "archive", "title": "AI 검토 결과", "markdown": "cross-owner",
    })
    assert crossed.status_code == 404
    assert not target.exists()

    created = await _request(app, "POST", "/api/contract-review/vault/notes", json={
        "snapshot_id": indexed["snapshot_id"], "vault_id": indexed["vault_id"],
        "folder": "archive", "title": "AI 검토 결과", "markdown": "# 분석\n\n명시적 저장",
    })
    assert created.status_code == 201
    assert created.json()["path"] == "archive/AI 검토 결과.md"
    assert str(workspace) not in created.text
    assert target.exists()


@pytest.mark.asyncio
async def test_context_route_rejects_job_ids_from_a_previous_mcp_runtime(contract_api):
    app, _workspace, _saved = contract_api
    response = await _request(app, "POST", "/api/contract-review/context/prepare", json={
        "session_id": "session-1",
        "snapshot_id": "snap",
        "vault_id": "vault",
        "selected_paths": [],
        "kordoc_job_ids": ["c" * 32],
        "law_job_ids": [],
        "mcp_runtime_id": "a" * 32,
    })
    assert response.status_code == 409
    assert response.json()["error"] == "stale_evidence_runtime"


@pytest.mark.asyncio
async def test_route_applies_compact_note_scope_to_search_open_and_context(contract_api):
    app, workspace, _saved = contract_api
    indexed = (await _request(app, "POST", "/api/contract-review/vault/index", json={
        "workspace": str(workspace), "vault_path": "vault",
    })).json()
    scope = {"default_included": False, "rules": [{"path": "Agreement.md", "included": True}]}

    search = await _request(app, "POST", "/api/contract-review/vault/search", json={
        "snapshot_id": indexed["snapshot_id"], "vault_id": indexed["vault_id"],
        "query": "MSA", "note_scope": scope,
    })
    assert search.status_code == 200
    assert [item["path"] for item in search.json()["results"]] == ["Agreement.md"]

    opened = await _request(app, "POST", "/api/contract-review/vault/open", json={
        "snapshot_id": indexed["snapshot_id"], "vault_id": indexed["vault_id"],
        "path": "archive/Hidden.md", "note_scope": scope,
    })
    assert opened.status_code == 403
    assert opened.json()["error"] == "outside_scope"

    prepared = await _request(app, "POST", "/api/contract-review/context/prepare", json={
        "session_id": "scope-session", "snapshot_id": indexed["snapshot_id"],
        "vault_id": indexed["vault_id"], "selected_paths": ["archive/Hidden.md"],
        "note_scope": scope, "kordoc_job_ids": [], "law_job_ids": [],
    })
    assert prepared.status_code == 403
    assert prepared.json()["error"] == "outside_scope"


@pytest.mark.asyncio
async def test_auth_disabled_uses_single_owner_namespace(contract_api, monkeypatch):
    app, workspace, _saved = contract_api
    monkeypatch.setenv("AUTH_ENABLED", "false")
    indexed = (await _request(app, "POST", "/api/contract-review/vault/index", owner=None, json={
        "workspace": str(workspace), "vault_path": "vault",
    })).json()
    result = await _request(app, "POST", "/api/contract-review/vault/search", owner=None, json={
        "snapshot_id": indexed["snapshot_id"], "vault_id": indexed["vault_id"], "query": "MSA",
    })
    assert result.status_code == 200
    assert result.json()["results"]


def test_contract_review_timeout_configuration_is_bounded(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_CONTRACT_REVIEW_KORDOC_TIMEOUT_SECONDS", "0.25")
    monkeypatch.setenv("ODYSSEUS_CONTRACT_REVIEW_LAW_TIMEOUT_SECONDS", "not-a-number")
    assert contract_review_timeouts_from_env() == (0.25, 60.0)

    monkeypatch.setenv("ODYSSEUS_CONTRACT_REVIEW_KORDOC_TIMEOUT_SECONDS", "0")
    monkeypatch.setenv("ODYSSEUS_CONTRACT_REVIEW_LAW_TIMEOUT_SECONDS", "99999")
    assert contract_review_timeouts_from_env() == (0.05, 900.0)
