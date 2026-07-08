import importlib
import json
import os
import stat
import sys
import types
from pathlib import Path


def _bridge_module():
    root = Path(__file__).resolve().parent.parent
    if "core" not in sys.modules:
        core = types.ModuleType("core")
        core.__path__ = [str(root / "core")]
        sys.modules["core"] = core
    sys.modules.pop("routes.codexian_bridge", None)
    return importlib.import_module("routes.codexian_bridge")


def test_sync_codexian_odysseus_session_updates_existing_settings(tmp_path):
    bridge = _bridge_module()
    data_path = tmp_path / "data.json"
    data_path.write_text(
        json.dumps(
            {
                "language": "ko",
                "odysseusLocal": {
                    "baseUrl": "http://localhost:7860",
                    "resultFolder": "00_수집함/Data Forge/결과",
                },
            }
        ),
        encoding="utf-8",
    )

    result = bridge.sync_codexian_odysseus_session(
        username="flytothesky",
        token="session-token",
        data_path=data_path,
    )

    assert result == {"updated": True}
    saved = json.loads(data_path.read_text(encoding="utf-8"))
    assert saved["language"] == "ko"
    assert saved["odysseusLocal"]["enabled"] is True
    assert saved["odysseusLocal"]["baseUrl"] == "http://localhost:7860"
    assert saved["odysseusLocal"]["authMode"] == "cookie"
    assert saved["odysseusLocal"]["authToken"] == "odysseus_session=session-token"
    assert saved["odysseusLocal"]["loginUsername"] == "flytothesky"
    assert saved["odysseusLocal"]["resultFolder"] == "00_수집함/Data Forge/결과"
    if os.name != "nt":
        assert stat.S_IMODE(data_path.stat().st_mode) == 0o600


def test_sync_codexian_odysseus_session_skips_missing_settings(tmp_path):
    bridge = _bridge_module()

    result = bridge.sync_codexian_odysseus_session(
        username="flytothesky",
        token="session-token",
        data_path=tmp_path / "missing.json",
    )

    assert result == {"updated": False, "reason": "codexian-settings-not-found"}


def test_sync_codexian_odysseus_session_skips_when_already_current(tmp_path):
    bridge = _bridge_module()
    data_path = tmp_path / "data.json"
    data_path.write_text(
        json.dumps(
            {
                "odysseusLocal": {
                    "enabled": True,
                    "authMode": "cookie",
                    "authToken": "odysseus_session=session-token",
                    "loginUsername": "flytothesky",
                },
            }
        ),
        encoding="utf-8",
    )

    result = bridge.sync_codexian_odysseus_session(
        username="flytothesky",
        token="session-token",
        data_path=data_path,
    )

    assert result == {"updated": False, "reason": "already-current"}


def test_sync_codexian_odysseus_session_can_be_disabled(tmp_path, monkeypatch):
    bridge = _bridge_module()
    data_path = tmp_path / "data.json"
    data_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEXIAN_OBSIDIAN_COOKIE_BRIDGE", "0")

    result = bridge.sync_codexian_odysseus_session(
        username="flytothesky",
        token="session-token",
        data_path=data_path,
    )

    assert result == {"updated": False, "reason": "disabled"}
    assert json.loads(data_path.read_text(encoding="utf-8")) == {}


def test_clear_codexian_odysseus_session_removes_cookie(tmp_path):
    bridge = _bridge_module()
    data_path = tmp_path / "data.json"
    data_path.write_text(
        json.dumps(
            {
                "language": "ko",
                "odysseusLocal": {
                    "enabled": True,
                    "baseUrl": "http://127.0.0.1:7860",
                    "authMode": "cookie",
                    "authToken": "odysseus_session=session-token",
                    "loginUsername": "flytothesky",
                    "resultFolder": "00_수집함/Data Forge/결과",
                },
            }
        ),
        encoding="utf-8",
    )

    result = bridge.clear_codexian_odysseus_session(data_path=data_path)

    assert result == {"updated": True}
    saved = json.loads(data_path.read_text(encoding="utf-8"))
    assert saved["language"] == "ko"
    assert saved["odysseusLocal"]["enabled"] is False
    assert saved["odysseusLocal"]["baseUrl"] == "http://127.0.0.1:7860"
    assert saved["odysseusLocal"]["authMode"] == "cookie"
    assert saved["odysseusLocal"]["authToken"] == ""
    assert saved["odysseusLocal"]["loginUsername"] == ""
    assert saved["odysseusLocal"]["resultFolder"] == "00_수집함/Data Forge/결과"
