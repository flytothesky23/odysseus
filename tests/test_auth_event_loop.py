"""Pin that the login handler keeps bcrypt off the event loop.

`/api/auth/login` is an `async def` and is reachable unauthenticated. bcrypt
(`checkpw`/`hashpw`) is deliberately CPU-expensive (~100-300 ms). Running it
directly in the coroutine blocks the single event loop for that whole window,
freezing every other in-flight request (chat streams, polling, ...). Because
the endpoint is unauthenticated and rate-limited only per-IP, a burst of login
attempts serializes the whole server — a cheap DoS-amplification vector.

The fix offloads the bcrypt-bearing AuthManager calls via asyncio.to_thread.
This test asserts those calls run on a worker thread, not the loop thread; it
fails if they are awaited inline again.
"""
import os
import sys
import types
import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock


# Stub `core.auth` / `core.database` before importing the route module.
# `routes.auth_routes` does `from core.auth import AuthManager`, and importing
# any `core.*` submodule first runs `core/__init__.py`, which transitively
# imports `src.llm_core` (hangs at import under the project venv) and the
# SQLAlchemy declarative models (metaclass blows up on a bare `core.database`
# import / under the conftest's `sqlalchemy.*` MagicMock stubs). We only need
# `AuthManager` as a type hint here — the handler is exercised with a MagicMock
# — so stub the heavy modules out. Same trick as test_auth_regressions.py /
# test_null_owner_gates.py.
def _ensure_stub(name: str, **attrs):
    """Create or augment a stub module, wiring it onto a stubbed parent package.

    Augments existing entries because an earlier-run test may have already
    stubbed the same module with a different attribute set. The parent package
    gets `__path__` pointed at the real on-disk dir so genuinely-unstubbed
    submodules still load normally, while `core/__init__.py` itself is bypassed
    (the package is already in `sys.modules`)."""
    if "." in name:
        parent_name, _, child_name = name.rpartition(".")
        if parent_name not in sys.modules:
            parent = types.ModuleType(parent_name)
            real_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                *parent_name.split("."),
            )
            parent.__path__ = [real_path] if os.path.isdir(real_path) else []
            sys.modules[parent_name] = parent
        else:
            parent = sys.modules[parent_name]
    else:
        parent = None
        child_name = None

    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    for k, v in attrs.items():
        if not hasattr(mod, k):
            setattr(mod, k, v)
    if parent is not None and not hasattr(parent, child_name):
        setattr(parent, child_name, mod)
    return mod


@pytest.fixture(autouse=True)
def _event_loop_stubs(monkeypatch):
    db = _ensure_stub("core.database", SessionLocal=MagicMock())
    auth = _ensure_stub("core.auth", AuthManager=MagicMock())
    monkeypatch.setitem(sys.modules, "core.database", db)
    monkeypatch.setitem(sys.modules, "core.auth", auth)


from routes.auth_routes import setup_auth_routes, LoginRequest


def _login_endpoint(auth_manager):
    router = setup_auth_routes(auth_manager)
    for r in router.routes:
        if getattr(r, "path", None) == "/api/auth/login" and "POST" in getattr(r, "methods", set()):
            return r.endpoint
    raise AssertionError("login route not found on the auth router")


def _status_endpoint(auth_manager):
    router = setup_auth_routes(auth_manager)
    for r in router.routes:
        if getattr(r, "path", None) == "/api/auth/status" and "GET" in getattr(r, "methods", set()):
            return r.endpoint
    raise AssertionError("status route not found on the auth router")


def _logout_endpoint(auth_manager):
    router = setup_auth_routes(auth_manager)
    for r in router.routes:
        if getattr(r, "path", None) == "/api/auth/logout" and "POST" in getattr(r, "methods", set()):
            return r.endpoint
    raise AssertionError("logout route not found on the auth router")


def test_login_offloads_bcrypt_bearing_calls(monkeypatch, tmp_path):
    calls = []
    auth = MagicMock()
    codexian_settings = tmp_path / "codexian-data.json"
    codexian_settings.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEXIAN_OBSIDIAN_PLUGIN_DATA", str(codexian_settings))

    async def fake_to_thread(fn, *args, **kwargs):
        calls.append(fn)
        return fn(*args, **kwargs)

    monkeypatch.setattr("routes.auth_routes.asyncio.to_thread", fake_to_thread)
    auth.verify_password.return_value = True
    auth.totp_enabled.return_value = False
    auth.create_session_trusted.return_value = "tok-123"

    login = _login_endpoint(auth)

    request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.7"), cookies={})
    response = MagicMock()
    body = LoginRequest(username="alice", password="hunter2", remember=True)

    result = asyncio.run(login(body=body, request=request, response=response))

    assert result["ok"] is True
    auth.verify_password.assert_called_once()
    auth.create_session_trusted.assert_called_once()
    # The whole point: the expensive bcrypt-bearing calls go through
    # asyncio.to_thread rather than running inline in the request coroutine.
    assert calls[:2] == [auth.verify_password, auth.create_session_trusted]
    assert getattr(calls[2], "__name__", "") == "sync_codexian_odysseus_session"


def test_auth_status_syncs_existing_session_cookie_to_codexian(monkeypatch, tmp_path):
    codexian_settings = tmp_path / "codexian-data.json"
    codexian_settings.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEXIAN_OBSIDIAN_PLUGIN_DATA", str(codexian_settings))

    auth = MagicMock()
    auth.signup_enabled = False
    auth.status.return_value = {"authenticated": True, "username": "alice"}
    auth.get_privileges.return_value = {"research": True}
    status = _status_endpoint(auth)

    request = SimpleNamespace(cookies={"odysseus_session": "tok-status"})
    result = asyncio.run(status(request=request))

    assert result["codexian_bridge"] == {"updated": True}
    saved = __import__("json").loads(codexian_settings.read_text(encoding="utf-8"))
    assert saved["odysseusLocal"]["authMode"] == "cookie"
    assert saved["odysseusLocal"]["authToken"] == "odysseus_session=tok-status"
    assert saved["odysseusLocal"]["loginUsername"] == "alice"


def test_auth_status_clears_codexian_when_cookie_is_invalid(monkeypatch, tmp_path):
    codexian_settings = tmp_path / "codexian-data.json"
    codexian_settings.write_text(
        '{"odysseusLocal":{"enabled":true,"authMode":"cookie","authToken":"odysseus_session=stale","loginUsername":"alice"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEXIAN_OBSIDIAN_PLUGIN_DATA", str(codexian_settings))

    auth = MagicMock()
    auth.signup_enabled = False
    auth.status.return_value = {"authenticated": False}
    status = _status_endpoint(auth)

    request = SimpleNamespace(cookies={"odysseus_session": "stale"})
    result = asyncio.run(status(request=request))

    assert result["codexian_bridge"] == {"updated": True}
    saved = __import__("json").loads(codexian_settings.read_text(encoding="utf-8"))
    assert saved["odysseusLocal"]["enabled"] is False
    assert saved["odysseusLocal"]["authToken"] == ""
    assert saved["odysseusLocal"]["loginUsername"] == ""


def test_logout_clears_codexian_cookie(monkeypatch, tmp_path):
    codexian_settings = tmp_path / "codexian-data.json"
    codexian_settings.write_text(
        '{"odysseusLocal":{"enabled":true,"authMode":"cookie","authToken":"odysseus_session=tok-logout","loginUsername":"alice"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEXIAN_OBSIDIAN_PLUGIN_DATA", str(codexian_settings))

    auth = MagicMock()
    logout = _logout_endpoint(auth)
    request = SimpleNamespace(cookies={"odysseus_session": "tok-logout"})
    response = MagicMock()

    result = asyncio.run(logout(request=request, response=response))

    assert result == {"ok": True}
    auth.revoke_token.assert_called_once_with("tok-logout")
    response.delete_cookie.assert_called_once_with("odysseus_session", path="/")
    saved = __import__("json").loads(codexian_settings.read_text(encoding="utf-8"))
    assert saved["odysseusLocal"]["enabled"] is False
    assert saved["odysseusLocal"]["authToken"] == ""
