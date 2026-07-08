"""Route-level owner-scope tests for persisted research reports."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routes.research_routes import setup_research_routes


@pytest.fixture(autouse=True)
def _redirect_research_dir(tmp_path, monkeypatch):
    # Deep-research paths are resolved from an import-time constant now, so chdir
    # no longer redirects them. Point the constant the routes read at the temp dir.
    monkeypatch.setattr(
        "routes.research_routes.DEEP_RESEARCH_DIR",
        str(tmp_path / "data" / "deep_research"),
    )


def _request(user: str, auth_manager=None):
    return SimpleNamespace(
        state=SimpleNamespace(current_user=user),
        app=SimpleNamespace(state=SimpleNamespace(auth_manager=auth_manager)),
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _route(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", "") != path:
            continue
        if method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"{method} {path} route not registered")


def _write_research(data_dir, session_id: str, **data):
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{session_id}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _research_handler():
    handler = MagicMock()
    handler._active_tasks = {}
    return handler


def test_local_folder_picker_allows_auth_disabled_single_user(tmp_path, monkeypatch):
    selected = tmp_path / "knowledge"
    selected.mkdir()
    saved = {"knowledge_local_roots": []}

    class FakeCompleted:
        returncode = 0
        stdout = str(selected) + "\n"
        stderr = ""

    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setattr("routes.research_routes.sys.platform", "darwin")
    monkeypatch.setattr("routes.research_routes.subprocess.run", lambda *args, **kwargs: FakeCompleted())
    monkeypatch.setattr("src.settings.load_settings", lambda: dict(saved))
    monkeypatch.setattr("src.settings.save_settings", lambda data: saved.update(data))
    monkeypatch.setattr(
        "src.knowledge_base.get_setting",
        lambda key, default=None: saved.get(key, default),
    )

    auth_manager = SimpleNamespace(is_configured=True, is_admin=lambda user: False)
    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/knowledge/local-folders/pick", "POST")

    out = asyncio.run(target(request=_request(None, auth_manager=auth_manager)))

    assert out["ok"] is True
    assert out["folder"]["path"] == str(selected.resolve())
    assert saved["knowledge_local_roots"][0]["path"] == str(selected.resolve())


def test_local_folder_picker_requires_admin_when_auth_enabled(tmp_path, monkeypatch):
    selected = tmp_path / "knowledge"
    selected.mkdir()
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setattr("routes.research_routes.sys.platform", "darwin")

    auth_manager = SimpleNamespace(is_configured=True, is_admin=lambda user: False)
    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/knowledge/local-folders/pick", "POST")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(request=_request("alice", auth_manager=auth_manager)))

    assert exc.value.status_code == 403


def test_local_folder_remove_allows_auth_disabled_single_user(tmp_path, monkeypatch):
    selected = tmp_path / "knowledge"
    selected.mkdir()
    saved = {
        "knowledge_local_roots": [
            {"id": "local123", "label": "Knowledge", "path": str(selected)}
        ]
    }

    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setattr("src.settings.load_settings", lambda: dict(saved))
    monkeypatch.setattr("src.settings.save_settings", lambda data: saved.update(data))
    monkeypatch.setattr(
        "src.knowledge_base.get_setting",
        lambda key, default=None: saved.get(key, default),
    )

    auth_manager = SimpleNamespace(is_configured=True, is_admin=lambda user: False)
    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/knowledge/local-folders/{root_id}", "DELETE")

    out = asyncio.run(target(root_id="local123", request=_request(None, auth_manager=auth_manager)))

    assert out == {"ok": True, "removed": True}
    assert saved["knowledge_local_roots"] == []


def test_local_folder_remove_requires_admin_when_auth_enabled(tmp_path, monkeypatch):
    selected = tmp_path / "knowledge"
    selected.mkdir()
    saved = {
        "knowledge_local_roots": [
            {"id": "local123", "label": "Knowledge", "path": str(selected)}
        ]
    }

    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setattr("src.settings.load_settings", lambda: dict(saved))
    monkeypatch.setattr("src.settings.save_settings", lambda data: saved.update(data))
    monkeypatch.setattr(
        "src.knowledge_base.get_setting",
        lambda key, default=None: saved.get(key, default),
    )

    auth_manager = SimpleNamespace(is_configured=True, is_admin=lambda user: False)
    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/knowledge/local-folders/{root_id}", "DELETE")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(root_id="local123", request=_request("alice", auth_manager=auth_manager)))

    assert exc.value.status_code == 403
    assert len(saved["knowledge_local_roots"]) == 1


def test_library_returns_only_caller_owned_unarchived_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "alice-live", owner="alice", query="Alice", completed_at=30)
    _write_research(data_dir, "alice-archived", owner="alice", query="Archived", archived=True)
    _write_research(data_dir, "bob-live", owner="bob", query="Bob", completed_at=40)
    _write_research(data_dir, "legacy-null", query="Legacy", completed_at=50)

    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/library", "GET")

    out = asyncio.run(target(
        request=_request("alice"),
        search=None,
        sort="recent",
        limit=50,
        archived=False,
    ))

    assert [item["id"] for item in out["research"]] == ["alice-live"]
    assert out["total"] == 1


def test_detail_rejects_cross_owner_and_null_owner_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "bob-report", owner="bob", result="bob secret")
    _write_research(data_dir, "legacy-report", result="legacy secret")

    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/detail/{session_id}", "GET")

    for session_id in ("bob-report", "legacy-report"):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(target(session_id=session_id, request=_request("alice")))
        assert exc.value.status_code == 404


def test_report_rejects_null_owner_before_generating_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "legacy-report", result="legacy secret")

    handler = _research_handler()
    router = setup_research_routes(handler)
    target = _route(router, "/api/research/report/{session_id}", "GET")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(session_id="legacy-report", request=_request("alice")))

    assert exc.value.status_code == 404
    handler.get_report_html.assert_not_called()


def test_markdown_export_rejects_cross_owner_before_generation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "bob-report", owner="bob", result="bob secret")

    handler = _research_handler()
    router = setup_research_routes(handler)
    target = _route(router, "/api/research/report/{session_id}/markdown", "GET")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(session_id="bob-report", request=_request("alice"), download=False))

    assert exc.value.status_code == 404
    handler.get_report_markdown.assert_not_called()


def test_session_json_export_rejects_cross_owner_before_generation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "bob-report", owner="bob", result="bob secret")

    handler = _research_handler()
    router = setup_research_routes(handler)
    target = _route(router, "/api/research/report/{session_id}/session.json", "GET")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(session_id="bob-report", request=_request("alice"), download=False))

    assert exc.value.status_code == 404
    handler.get_report_session_export.assert_not_called()


def test_archive_rejects_cross_owner_without_mutating_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    path = _write_research(data_dir, "bob-report", owner="bob", archived=False)

    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/{session_id}/archive", "POST")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(session_id="bob-report", request=_request("alice"), archived=True))

    assert exc.value.status_code == 404
    assert json.loads(path.read_text(encoding="utf-8"))["archived"] is False


def test_delete_rejects_cross_owner_without_unlinking_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    path = _write_research(data_dir, "bob-report", owner="bob", result="bob secret")

    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/{session_id}", "DELETE")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(session_id="bob-report", request=_request("alice")))

    assert exc.value.status_code == 404
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["result"] == "bob secret"
