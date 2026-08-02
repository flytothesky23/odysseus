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


def _request(user: str, *, admin: bool = False):
    auth_manager = SimpleNamespace(
        is_configured=True,
        is_admin=lambda candidate: admin and candidate == user,
    )
    return SimpleNamespace(
        state=SimpleNamespace(current_user=user),
        app=SimpleNamespace(state=SimpleNamespace(auth_manager=auth_manager)),
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


def test_designed_report_rejects_cross_owner_before_generating_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "bob-designed", owner="bob", result="bob secret")

    handler = _research_handler()
    router = setup_research_routes(handler)
    target = _route(router, "/api/research/report/{session_id}/designed", "GET")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(session_id="bob-designed", request=_request("alice")))

    assert exc.value.status_code == 404
    handler.get_report_html.assert_not_called()


def test_renderer_route_is_owner_scoped_allowlisted_and_downloadable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "alice-gallery", owner="alice", result="safe")

    handler = _research_handler()
    handler.get_report_html.return_value = "<!doctype html><title>ok</title>"
    router = setup_research_routes(handler)
    target = _route(
        router,
        "/api/research/report/{session_id}/renderer/{renderer_id}",
        "GET",
    )

    response = asyncio.run(target(
        session_id="alice-gallery",
        renderer_id="scroll_story",
        request=_request("alice"),
        download=True,
    ))

    assert response.status_code == 200
    assert "scroll-story.html" in response.headers["content-disposition"]
    handler.get_report_html.assert_called_once_with(
        "alice-gallery",
        renderer="scroll_story",
    )

    handler.reset_mock()
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(target(
            session_id="alice-gallery",
            renderer_id="../script",
            request=_request("alice"),
            download=False,
        ))
    assert invalid.value.status_code == 404
    handler.get_report_html.assert_not_called()


def test_renderer_route_rejects_cross_owner_before_rendering(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "bob-gallery", owner="bob", result="bob secret")

    handler = _research_handler()
    router = setup_research_routes(handler)
    target = _route(
        router,
        "/api/research/report/{session_id}/renderer/{renderer_id}",
        "GET",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(
            session_id="bob-gallery",
            renderer_id="document",
            request=_request("alice"),
            download=False,
        ))

    assert exc.value.status_code == 404
    handler.get_report_html.assert_not_called()


def test_renderer_route_surfaces_generation_failure_as_500(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "deep_research"
    _write_research(data_dir, "alice-broken", owner="alice", result="safe")

    handler = _research_handler()
    handler.get_report_html.side_effect = RuntimeError("renderer failed")
    router = setup_research_routes(handler)
    target = _route(
        router,
        "/api/research/report/{session_id}/renderer/{renderer_id}",
        "GET",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(
            session_id="alice-broken",
            renderer_id="scroll_story",
            request=_request("alice"),
            download=False,
        ))

    assert exc.value.status_code == 500
    handler.get_report_html.assert_called_once_with(
        "alice-broken",
        renderer="scroll_story",
    )


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


def test_markdown_export_rejects_cross_owner_before_generating(tmp_path, monkeypatch):
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


def test_local_folder_delete_only_removes_settings_not_files(tmp_path, monkeypatch):
    local = tmp_path / "datasets"
    local.mkdir()
    kept_file = local / "metrics.json"
    kept_file.write_text('{"ok": true}', encoding="utf-8")
    settings = {"knowledge_local_roots": [{"id": "local123", "label": "Datasets", "path": str(local)}]}

    monkeypatch.setattr("src.settings.load_settings", lambda: dict(settings))

    def fake_save(updated):
        settings.clear()
        settings.update(updated)

    monkeypatch.setattr("src.settings.save_settings", fake_save)

    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/knowledge/local-folders/{root_id}", "DELETE")

    out = asyncio.run(target(root_id="local123", request=_request("alice", admin=True)))

    assert out == {"ok": True, "removed": True}
    assert kept_file.exists()
    assert settings["knowledge_local_roots"] == []


def test_local_folder_delete_rejects_non_admin(tmp_path, monkeypatch):
    local = tmp_path / "datasets"
    local.mkdir()
    settings = {"knowledge_local_roots": [{"id": "local123", "label": "Datasets", "path": str(local)}]}
    monkeypatch.setattr("src.settings.load_settings", lambda: dict(settings))

    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/knowledge/local-folders/{root_id}", "DELETE")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(root_id="local123", request=_request("alice")))

    assert exc.value.status_code == 403
    assert settings["knowledge_local_roots"]


def test_knowledge_settings_rejects_non_admin():
    router = setup_research_routes(_research_handler())
    target = _route(router, "/api/research/knowledge/settings", "GET")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(target(request=_request("alice")))

    assert exc.value.status_code == 403


def test_editorial_start_rejects_web_or_implicit_all_roots(monkeypatch):
    handler = _research_handler()
    monkeypatch.setattr(
        "routes.research_routes.resolve_endpoint",
        lambda *_args, **_kwargs: ("http://fake.invalid/v1/chat/completions", "fake", {}),
    )
    monkeypatch.setattr("src.auth_helpers.require_privilege", lambda _request, _name: "alice")
    router = setup_research_routes(handler)
    target = _route(router, "/api/research/start", "POST")
    request_type = target.__annotations__["body"]

    for body in (
        request_type(
            query="private report",
            research_mode="editorial",
            source_mode="web",
            knowledge_folders=["obsidian:project"],
        ),
        request_type(
            query="private report",
            research_mode="editorial",
            source_mode="obsidian",
            knowledge_folders=[],
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(target(body=body, request=_request("alice", admin=True)))
        assert exc.value.status_code == 400

    handler.start_research.assert_not_called()


def test_legacy_designed_format_without_renderer_keeps_editorial_contract(monkeypatch):
    handler = _research_handler()
    handler.start_research.return_value = {
        "html_renderers": ["editorial"],
        "design_image_mode": "editorial",
    }
    monkeypatch.setattr(
        "routes.research_routes.resolve_endpoint",
        lambda *_args, **_kwargs: ("http://fake.invalid/v1/chat/completions", "fake", {}),
    )
    monkeypatch.setattr("src.auth_helpers.require_privilege", lambda _request, _name: "alice")
    router = setup_research_routes(handler)
    target = _route(router, "/api/research/start", "POST")
    request_type = target.__annotations__["body"]

    response = asyncio.run(target(
        body=request_type(
            query="legacy designed report",
            artifact_formats=["html_designed"],
            design_image_mode="editorial",
        ),
        request=_request("alice"),
    ))

    assert response["html_renderers"] == ["editorial"]
    assert response["design_image_mode"] == "editorial"
    kwargs = handler.start_research.call_args.kwargs
    assert kwargs["artifact_formats"] == ["html_designed"]
    assert kwargs["html_renderers"] == []
