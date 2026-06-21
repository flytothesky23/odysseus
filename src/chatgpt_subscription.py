"""ChatGPT subscription / Codex backend OAuth helpers.

This provider is intentionally separate from OpenAI API-key endpoints. It uses
OpenAI account OAuth device authorization, stores refresh tokens server-side,
and resolves a fresh bearer token at request time.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

DEFAULT_CHATGPT_SUBSCRIPTION_BASE_URL = (
    os.getenv("CHATGPT_SUBSCRIPTION_BASE_URL", "").strip().rstrip("/")
    or "https://chatgpt.com/backend-api/codex"
)
CHATGPT_SUBSCRIPTION_PROVIDER = "chatgpt-subscription"
CHATGPT_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CHATGPT_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CHATGPT_OAUTH_ISSUER = "https://auth.openai.com"
CHATGPT_OAUTH_REDIRECT_URI = f"{CHATGPT_OAUTH_ISSUER}/deviceauth/callback"
CHATGPT_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120
_AUTH_REFRESH_LOCKS: dict[str, threading.Lock] = {}
_AUTH_REFRESH_LOCKS_GUARD = threading.Lock()


def _database_handles():
    from core.database import ProviderAuthSession, SessionLocal, utcnow_naive
    return ProviderAuthSession, SessionLocal, utcnow_naive


def _refresh_lock_for(auth_id: str) -> threading.Lock:
    with _AUTH_REFRESH_LOCKS_GUARD:
        lock = _AUTH_REFRESH_LOCKS.get(auth_id)
        if lock is None:
            lock = threading.Lock()
            _AUTH_REFRESH_LOCKS[auth_id] = lock
        return lock


class ChatGPTSubscriptionError(RuntimeError):
    """Base error for ChatGPT subscription provider failures."""


class ChatGPTSubscriptionReauthRequired(ChatGPTSubscriptionError):
    """Stored OAuth credentials are invalid or expired beyond refresh."""


class ChatGPTSubscriptionRateLimited(ChatGPTSubscriptionError):
    """Upstream quota/rate limit; reconnecting will not fix it."""


class ChatGPTSubscriptionAuthNotFound(ChatGPTSubscriptionError):
    """No matching owner-scoped auth session exists."""


class CodexCliAuthNotFound(ChatGPTSubscriptionError):
    """No usable Codex CLI ChatGPT login was found on this machine."""


def is_chatgpt_subscription_base(url: str) -> bool:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower().rstrip(".")
        path = (parsed.path or "").rstrip("/")
    except Exception:
        return False
    return host == "chatgpt.com" and (
        path == "/backend-api/codex" or path.startswith("/backend-api/codex/")
    )


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        try:
            key = str(path.expanduser())
        except Exception:
            continue
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(Path(key))
    return out


def codex_cli_auth_candidates(explicit_path: Optional[str] = None) -> list[Path]:
    """Return likely Codex CLI auth.json locations without reading secrets."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    env_auth = os.getenv("CODEX_AUTH_FILE", "").strip()
    if env_auth:
        candidates.append(Path(env_auth))
    codex_home = os.getenv("CODEX_HOME", "").strip()
    if codex_home:
        candidates.append(Path(codex_home) / "auth.json")
    candidates.extend([
        Path("~/.codex/auth.json"),
        Path("~/Library/Application Support/Codex/auth.json"),
        Path("~/.config/codex/auth.json"),
    ])
    return _dedupe_paths(candidates)


def find_codex_cli_auth_file(explicit_path: Optional[str] = None) -> Optional[Path]:
    for candidate in codex_cli_auth_candidates(explicit_path):
        path = candidate.expanduser()
        if path.is_file():
            return path
    return None


def codex_cli_auth_status(explicit_path: Optional[str] = None) -> Dict[str, Any]:
    """Return a redacted status object for UI diagnostics."""
    path = find_codex_cli_auth_file(explicit_path)
    if not path:
        return {
            "found": False,
            "path": str(codex_cli_auth_candidates(explicit_path)[0].expanduser())
            if codex_cli_auth_candidates(explicit_path) else "",
            "auth_mode": "",
            "has_chatgpt_tokens": False,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "found": True,
            "path": str(path),
            "auth_mode": "",
            "has_chatgpt_tokens": False,
            "error": "Codex CLI auth file is not readable JSON.",
        }
    tokens = data.get("tokens") if isinstance(data, dict) else {}
    tokens = tokens if isinstance(tokens, dict) else {}
    has_chatgpt_tokens = bool(tokens.get("access_token") and tokens.get("refresh_token"))
    return {
        "found": True,
        "path": str(path),
        "auth_mode": str(data.get("auth_mode") or ""),
        "has_chatgpt_tokens": has_chatgpt_tokens,
        "has_api_key": bool(data.get("OPENAI_API_KEY")),
        "account_hint": str(tokens.get("account_id") or "")[:8] if tokens.get("account_id") else "",
    }


def read_codex_cli_chatgpt_tokens(explicit_path: Optional[str] = None) -> Dict[str, Any]:
    """Read ChatGPT OAuth tokens from the local Codex CLI auth file.

    The returned dict is suitable for the existing ChatGPT Subscription
    provisioning path. Callers must not log token values.
    """
    path = find_codex_cli_auth_file(explicit_path)
    if not path:
        raise CodexCliAuthNotFound(
            "Codex CLI auth.json was not found. Run `codex login` first, then import again."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CodexCliAuthNotFound(f"Codex CLI auth file could not be read: {path}") from exc
    if not isinstance(data, dict):
        raise CodexCliAuthNotFound("Codex CLI auth file has an unexpected format.")
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        raise CodexCliAuthNotFound(
            "Codex CLI is present, but no ChatGPT login tokens were found. Run `codex login` instead of API-key-only auth."
        )
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not access_token or not refresh_token:
        raise CodexCliAuthNotFound(
            "Codex CLI auth exists, but it does not contain a ChatGPT access/refresh token pair."
        )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": tokens.get("id_token"),
        "account_id": tokens.get("account_id"),
        "auth_mode": data.get("auth_mode") or "chatgpt",
        "source_path": str(path),
    }


def chatgpt_headers(access_token: Optional[str]) -> Dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/codex",
        "User-Agent": "Odysseus ChatGPT Subscription",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def fetch_available_models(access_token: str, timeout: float = 10.0) -> list[str]:
    if not access_token:
        return []
    try:
        response = httpx.get(
            "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0",
            headers=chatgpt_headers(access_token),
            timeout=timeout,
        )
        if response.status_code != 200:
            return []
        data = response.json()
    except Exception:
        return []
    entries = data.get("models", []) if isinstance(data, dict) else []
    sortable: list[tuple[int, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        visibility = item.get("visibility", "")
        if isinstance(visibility, str) and visibility.strip().lower() in {"hide", "hidden"}:
            continue
        priority = item.get("priority")
        rank = int(priority) if isinstance(priority, (int, float)) else 10_000
        sortable.append((rank, slug.strip()))
    sortable.sort(key=lambda item: (item[0], item[1]))
    ordered: list[str] = []
    seen: set[str] = set()
    for _, slug in sortable:
        if slug not in seen:
            ordered.append(slug)
            seen.add(slug)
    return ordered


def _raise_for_oauth_response(response: httpx.Response, action: str) -> None:
    if response.status_code < 400:
        return
    code = ""
    message = f"ChatGPT Subscription {action} failed with HTTP {response.status_code}."
    try:
        payload = response.json()
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or "").strip()
            msg = err.get("message")
            if msg:
                message = f"ChatGPT Subscription {action} failed: {msg}"
        elif isinstance(err, str):
            code = err.strip()
            desc = payload.get("error_description") or payload.get("message")
            if desc:
                message = f"ChatGPT Subscription {action} failed: {desc}"
    except Exception:
        pass
    if response.status_code == 429:
        raise ChatGPTSubscriptionRateLimited(
            "ChatGPT Subscription quota or rate limit was reached. Credentials are still valid."
        )
    if response.status_code in (401, 403) or code in {"invalid_grant", "invalid_token", "invalid_request", "refresh_token_reused"}:
        raise ChatGPTSubscriptionReauthRequired(message)
    raise ChatGPTSubscriptionError(message)


def _json_or_error(response: httpx.Response, action: str) -> Dict[str, Any]:
    _raise_for_oauth_response(response, action)
    try:
        data = response.json()
    except Exception as exc:
        raise ChatGPTSubscriptionError(f"ChatGPT Subscription {action} returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise ChatGPTSubscriptionError(f"ChatGPT Subscription {action} returned an unexpected response.")
    return data


def request_device_code(timeout: float = 15.0) -> Dict[str, Any]:
    response = httpx.post(
        f"{CHATGPT_OAUTH_ISSUER}/api/accounts/deviceauth/usercode",
        json={"client_id": CHATGPT_OAUTH_CLIENT_ID},
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    data = _json_or_error(response, "device-code request")
    if not data.get("device_auth_id") or not data.get("user_code"):
        raise ChatGPTSubscriptionError("ChatGPT device-code response was missing required fields.")
    data.setdefault("verification_uri", f"{CHATGPT_OAUTH_ISSUER}/codex/device")
    data.setdefault("interval", 5)
    data.setdefault("expires_in", 900)
    return data


def poll_device_auth(device_auth_id: str, user_code: str, timeout: float = 15.0) -> Dict[str, Any]:
    response = httpx.post(
        f"{CHATGPT_OAUTH_ISSUER}/api/accounts/deviceauth/token",
        json={"device_auth_id": device_auth_id, "user_code": user_code},
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    if response.status_code in (403, 404):
        return {"status": "pending", "error": "authorization_pending"}
    return _json_or_error(response, "device-code poll")


def exchange_authorization_code(authorization_code: str, code_verifier: str, timeout: float = 15.0) -> Dict[str, Any]:
    response = httpx.post(
        CHATGPT_OAUTH_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": CHATGPT_OAUTH_REDIRECT_URI,
            "client_id": CHATGPT_OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        timeout=timeout,
    )
    data = _json_or_error(response, "token exchange")
    if not data.get("access_token"):
        raise ChatGPTSubscriptionReauthRequired("ChatGPT token exchange did not return an access token.")
    return data


def refresh_oauth_tokens(access_token: str, refresh_token: str, timeout: float = 20.0) -> Dict[str, Any]:
    del access_token
    if not refresh_token:
        raise ChatGPTSubscriptionReauthRequired("ChatGPT Subscription is missing a refresh token. Reconnect the provider.")
    response = httpx.post(
        CHATGPT_OAUTH_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CHATGPT_OAUTH_CLIENT_ID,
        },
        timeout=timeout,
    )
    data = _json_or_error(response, "token refresh")
    if not data.get("access_token"):
        raise ChatGPTSubscriptionReauthRequired("ChatGPT token refresh did not return an access token.")
    return data


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    parts = (token or "").split(".")
    if len(parts) < 2:
        raise ValueError("not a JWT")
    segment = parts[1]
    segment += "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode(segment.encode("ascii"))
    payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def access_token_is_expiring(access_token: str, skew_seconds: int = CHATGPT_ACCESS_TOKEN_REFRESH_SKEW_SECONDS) -> bool:
    try:
        exp = int(_decode_jwt_payload(access_token).get("exp") or 0)
    except Exception:
        return True
    return exp <= int(time.time()) + int(skew_seconds)


def resolve_runtime_credentials(auth_id: str, owner: Optional[str] = None, *, force_refresh: bool = False) -> Dict[str, Any]:
    ProviderAuthSession, SessionLocal, utcnow_naive = _database_handles()
    db = SessionLocal()
    try:
        q = db.query(ProviderAuthSession).filter(
            ProviderAuthSession.id == auth_id,
            ProviderAuthSession.provider == CHATGPT_SUBSCRIPTION_PROVIDER,
        )
        if owner:
            q = q.filter(ProviderAuthSession.owner == owner)
        row = q.first()
        if row is None:
            raise ChatGPTSubscriptionAuthNotFound("ChatGPT Subscription credentials were not found for this user.")

        access_token = row.access_token or ""
        if force_refresh or access_token_is_expiring(access_token):
            with _refresh_lock_for(auth_id):
                db.refresh(row)
                access_token = row.access_token or ""
                refresh_token = row.refresh_token or ""
                if force_refresh or access_token_is_expiring(access_token):
                    refreshed = refresh_oauth_tokens(access_token, refresh_token)
                    row.access_token = refreshed["access_token"]
                    if refreshed.get("refresh_token"):
                        row.refresh_token = refreshed["refresh_token"]
                    row.last_refresh = utcnow_naive()
                    db.commit()
                    db.refresh(row)
            access_token = row.access_token or ""

        return {
            "provider": CHATGPT_SUBSCRIPTION_PROVIDER,
            "base_url": (row.base_url or DEFAULT_CHATGPT_SUBSCRIPTION_BASE_URL).rstrip("/"),
            "api_key": access_token,
            "auth_mode": row.auth_mode or "chatgpt",
        }
    finally:
        db.close()


def to_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, CodexCliAuthNotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, ChatGPTSubscriptionRateLimited):
        return HTTPException(429, str(exc))
    if isinstance(exc, (ChatGPTSubscriptionReauthRequired, ChatGPTSubscriptionAuthNotFound)):
        return HTTPException(401, f"{exc} Reconnect the provider.")
    return HTTPException(502, str(exc))


def build_responses_input(messages: list[dict]) -> list[dict]:
    input_items: list[dict] = []
    for msg in messages or []:
        role = msg.get("role") or "user"
        if role == "tool":
            role = "user"
        content = msg.get("content")
        if isinstance(content, list):
            text = "\n".join(str(part.get("text") or part.get("content") or "") for part in content if isinstance(part, dict))
        else:
            text = "" if content is None else str(content)
        input_type = "output_text" if role == "assistant" else "input_text"
        input_items.append({"role": role, "content": [{"type": input_type, "text": text}]})
    return input_items
