"""Local-only bridge for sharing Odysseus login sessions with Codexian."""

from __future__ import annotations

import json
import ipaddress
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from core.atomic_io import atomic_write_json
from src.settings import get_setting

logger = logging.getLogger(__name__)

CODEXIAN_BRIDGE_ENV = "CODEXIAN_OBSIDIAN_COOKIE_BRIDGE"
CODEXIAN_DATA_PATH_ENV = "CODEXIAN_OBSIDIAN_PLUGIN_DATA"
SESSION_COOKIE_NAME = "odysseus_session"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:7860"

DEFAULT_CODEXIAN_DATA_PATH = (
    Path.home()
    / "Library/Application Support/ObsidianLocalVaults/GoogleDrive-Notes-MacBook/.obsidian/plugins/codexian/data.json"
)


def resolve_codexian_data_path() -> Path:
    configured = os.getenv(CODEXIAN_DATA_PATH_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_CODEXIAN_DATA_PATH


def sync_codexian_odysseus_session(
    *,
    username: str,
    token: str,
    base_url: str = DEFAULT_LOCAL_BASE_URL,
    data_path: Path | None = None,
) -> dict[str, Any]:
    """Persist the current Odysseus session cookie into Codexian settings."""

    if not _bridge_enabled():
        return {"updated": False, "reason": "disabled"}

    username = username.strip()
    token = token.strip()
    if not username or not token:
        return {"updated": False, "reason": "missing-session"}

    path = data_path or resolve_codexian_data_path()
    if not path.exists():
        return {"updated": False, "reason": "codexian-settings-not-found"}

    try:
        data = _read_settings(path)
        odysseus_local = data.get("odysseusLocal")
        if not isinstance(odysseus_local, dict):
            odysseus_local = {}

        cookie_value = f"{SESSION_COOKIE_NAME}={token}"
        next_odysseus_local = dict(odysseus_local)
        existing_base_url = next_odysseus_local.get("baseUrl")
        candidate_base_url = (
            existing_base_url.strip()
            if isinstance(existing_base_url, str) and existing_base_url.strip()
            else base_url
        )
        normalized_base_url = _safe_loopback_base_url(candidate_base_url, fallback=base_url)
        if (
            next_odysseus_local.get("enabled") is True
            and next_odysseus_local.get("baseUrl") == normalized_base_url
            and next_odysseus_local.get("authMode") == "cookie"
            and next_odysseus_local.get("authToken") == cookie_value
            and next_odysseus_local.get("loginUsername") == username
        ):
            return {"updated": False, "reason": "already-current"}

        next_odysseus_local.update(
            {
                "enabled": True,
                "baseUrl": normalized_base_url,
                "authMode": "cookie",
                "authToken": cookie_value,
                "loginUsername": username,
            }
        )
        data["odysseusLocal"] = next_odysseus_local

        atomic_write_json(str(path), data, indent=2)
        _chmod_user_only(path)
        return {"updated": True}
    except Exception:
        logger.exception("Codexian local bridge failed to update plugin settings")
        return {"updated": False, "reason": "write-failed"}


def clear_codexian_odysseus_session(*, data_path: Path | None = None) -> dict[str, Any]:
    """Clear the bridged Odysseus cookie when the browser session is gone."""

    if not _bridge_enabled():
        return {"updated": False, "reason": "disabled"}

    path = data_path or resolve_codexian_data_path()
    if not path.exists():
        return {"updated": False, "reason": "codexian-settings-not-found"}

    try:
        data = _read_settings(path)
        odysseus_local = data.get("odysseusLocal")
        if not isinstance(odysseus_local, dict):
            return {"updated": False, "reason": "already-current"}

        next_odysseus_local = dict(odysseus_local)
        already_clear = (
            next_odysseus_local.get("enabled") is False
            and not next_odysseus_local.get("authToken")
            and not next_odysseus_local.get("loginUsername")
        )
        if already_clear:
            return {"updated": False, "reason": "already-current"}

        next_odysseus_local.update(
            {
                "enabled": False,
                "authMode": "cookie",
                "authToken": "",
                "loginUsername": "",
            }
        )
        data["odysseusLocal"] = next_odysseus_local
        atomic_write_json(str(path), data, indent=2)
        _chmod_user_only(path)
        return {"updated": True}
    except Exception:
        logger.exception("Codexian local bridge failed to clear plugin settings")
        return {"updated": False, "reason": "write-failed"}


def _bridge_enabled() -> bool:
    env_value = os.getenv(CODEXIAN_BRIDGE_ENV, "").strip().lower()
    if env_value in {"0", "false", "no", "off"}:
        return False
    return bool(get_setting("codexian_cookie_bridge_enabled", True))


def _safe_loopback_base_url(value: str, *, fallback: str = DEFAULT_LOCAL_BASE_URL) -> str:
    """Return a loopback HTTP(S) URL, replacing unsafe cookie destinations."""

    def _is_safe(candidate: str) -> bool:
        try:
            parsed = urlsplit(candidate)
            if parsed.scheme.lower() not in {"http", "https"}:
                return False
            if not parsed.hostname or parsed.username is not None or parsed.password is not None:
                return False
            # Force validation of malformed/out-of-range ports.
            _ = parsed.port
            hostname = parsed.hostname.rstrip(".").lower()
            if hostname == "localhost":
                return True
            return ipaddress.ip_address(hostname).is_loopback
        except (ValueError, UnicodeError):
            return False

    normalized = str(value or "").strip()
    if _is_safe(normalized):
        return normalized
    safe_fallback = str(fallback or "").strip()
    return safe_fallback if _is_safe(safe_fallback) else DEFAULT_LOCAL_BASE_URL


def _read_settings(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Codexian settings file must contain a JSON object")
    return data


def _chmod_user_only(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o600)
    except OSError:
        logger.debug("Could not chmod Codexian settings file", exc_info=True)
