"""ChatGPT Subscription device-flow setup routes."""

import json
import logging
import uuid
from typing import Dict, Optional

from fastapi import Form, HTTPException, Request

from core.database import ModelEndpoint, ProviderAuthSession, SessionLocal, utcnow_naive
from core.middleware import require_admin
from routes.device_flow import (
    DeviceFlowPoll,
    DeviceFlowStart,
    PendingDeviceFlowStore,
    create_device_flow_router,
)
from src.auth_helpers import get_current_user
from src import chatgpt_subscription

logger = logging.getLogger(__name__)

_DEVICE_FLOW_STORE = PendingDeviceFlowStore()


def _preferred_utility_model(models: list[str]) -> str:
    for candidate in ("gpt-5.3-codex-spark", "gpt-5.4-mini"):
        if candidate in models:
            return candidate
    return models[0] if models else ""


def _apply_endpoint_defaults(ep_id: str, models: list[str], *, force: bool = False) -> None:
    if not ep_id or not models:
        return
    try:
        from src.endpoint_resolver import _first_chat_model
        from src.settings import load_settings, save_settings

        default_model = _first_chat_model(models) or models[0]
        utility_model = _preferred_utility_model(models)
        settings = load_settings()
        changed = False

        if force or not settings.get("default_endpoint_id"):
            settings["default_endpoint_id"] = ep_id
            settings["default_model"] = default_model
            changed = True

        if force:
            settings["utility_endpoint_id"] = ep_id
            settings["utility_model"] = utility_model
            settings["research_endpoint_id"] = ep_id
            settings["research_model"] = default_model
            settings["task_endpoint_id"] = ep_id
            settings["task_model"] = utility_model
            changed = True

        if changed:
            save_settings(settings)
    except Exception:
        logger.exception("Failed to apply ChatGPT Subscription endpoint defaults")


def _repair_empty_chat_sessions(owner: Optional[str], endpoint_url: str, model: str) -> int:
    """Point placeholder sessions at the newly imported provider.

    Existing message-bearing sessions keep their selected model. Empty sessions
    with no endpoint are usually first-run placeholders; without this repair the
    first chat can still say no model is selected after a successful import.
    """
    if not endpoint_url or not model:
        return 0
    from core.database import Session as DbSession
    from src.endpoint_resolver import build_chat_url

    chat_url = build_chat_url(endpoint_url)
    db = SessionLocal()
    repaired = 0
    changed = False
    try:
        q = db.query(DbSession).filter(
            DbSession.archived == False,  # noqa: E712
        )
        if owner:
            q = q.filter(DbSession.owner == owner)
        for row in q.all():
            row_url = (row.endpoint_url or "").strip().rstrip("/")
            is_subscription_session = row_url == chat_url.rstrip("/") or row_url.startswith(endpoint_url.rstrip("/") + "/")
            if is_subscription_session and row.headers:
                # Never persist short-lived ChatGPT/Codex bearer headers in the
                # plain session row; resolve them from provider_auth_sessions.
                row.headers = {}
                changed = True
            if (row.message_count or 0) != 0:
                continue
            if row_url and (row.model or "").strip():
                continue
            row.endpoint_url = chat_url
            row.model = model
            # ChatGPT Subscription bearer headers are resolved request-locally.
            row.headers = {}
            row.updated_at = utcnow_naive()
            repaired += 1
            changed = True
        if changed:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to repair empty chat sessions after Codex CLI import")
    finally:
        db.close()
    return repaired


def _provision_endpoint(
    tokens: Dict,
    owner: Optional[str],
    *,
    auth_label: str = "ChatGPT Subscription",
    endpoint_name: str = "ChatGPT Subscription",
    force_default: bool = False,
) -> Dict:
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not access_token or not refresh_token:
        raise ValueError("ChatGPT token response was missing access_token or refresh_token")

    base = chatgpt_subscription.DEFAULT_CHATGPT_SUBSCRIPTION_BASE_URL
    models = chatgpt_subscription.fetch_available_models(access_token)
    if not models:
        raise ValueError("ChatGPT Subscription connected, but no usable Codex models were discovered for this account.")
    db = SessionLocal()
    try:
        auth = (
            db.query(ProviderAuthSession)
            .filter(
                ProviderAuthSession.provider == chatgpt_subscription.CHATGPT_SUBSCRIPTION_PROVIDER,
                ProviderAuthSession.owner == owner,
            )
            .first()
        )
        if auth is None:
            auth = ProviderAuthSession(
                id=str(uuid.uuid4())[:8],
                provider=chatgpt_subscription.CHATGPT_SUBSCRIPTION_PROVIDER,
                owner=owner,
                label=auth_label,
                base_url=base,
                auth_mode="chatgpt",
            )
            db.add(auth)
        auth.label = auth_label
        auth.base_url = base
        auth.access_token = access_token
        auth.refresh_token = refresh_token
        auth.last_refresh = utcnow_naive()
        auth.auth_mode = "chatgpt"

        ep = (
            db.query(ModelEndpoint)
            .filter(
                ModelEndpoint.base_url == base,
                ModelEndpoint.provider_auth_id == auth.id,
                ModelEndpoint.owner == owner,
            )
            .first()
        )
        if ep is None:
            ep = ModelEndpoint(
                id=str(uuid.uuid4())[:8],
                name=endpoint_name,
                base_url=base,
                model_type="llm",
                endpoint_kind="api",
                owner=owner,
            )
            db.add(ep)
        ep.name = endpoint_name
        ep.base_url = base
        ep.api_key = None
        ep.provider_auth_id = auth.id
        ep.is_enabled = True
        ep.supports_tools = False
        ep.model_type = "llm"
        ep.endpoint_kind = "api"
        ep.model_refresh_mode = "manual"
        ep.cached_models = json.dumps(models)
        db.commit()
        result = {
            "id": ep.id,
            "name": ep.name,
            "base_url": ep.base_url,
            "models": models,
        }
    finally:
        db.close()

    try:
        from routes.model_routes import _invalidate_models_cache

        _invalidate_models_cache()
    except Exception:
        pass
    _apply_endpoint_defaults(result["id"], models, force=force_default)
    repaired = _repair_empty_chat_sessions(owner, base, models[0] if models else "")
    result["repaired_empty_sessions"] = repaired
    result["default_applied"] = bool(force_default)
    return result


def _start_device_flow(request: Request, _form) -> DeviceFlowStart:
    try:
        data = chatgpt_subscription.request_device_code()
    except Exception as exc:
        raise chatgpt_subscription.to_http_exception(exc)

    device_auth_id = data.get("device_auth_id")
    user_code = data.get("user_code")
    if not device_auth_id or not user_code:
        raise HTTPException(502, "ChatGPT did not return a complete device code")
    verification_uri = data.get("verification_uri") or f"{chatgpt_subscription.CHATGPT_OAUTH_ISSUER}/codex/device"
    return DeviceFlowStart(
        pending={
            "device_auth_id": device_auth_id,
            "user_code": user_code,
            "owner": get_current_user(request) or None,
        },
        response={
            "user_code": user_code,
            "verification_uri": verification_uri,
        },
        interval=int(data.get("interval") or 5),
        expires_in=int(data.get("expires_in") or 900),
    )


def _poll_device_flow(_request: Request, pending: Dict) -> DeviceFlowPoll:
    try:
        data = chatgpt_subscription.poll_device_auth(pending["device_auth_id"], pending["user_code"])
    except Exception as exc:
        logger.debug("ChatGPT device poll failed: %s", exc)
        return DeviceFlowPoll.pending(str(exc))

    authorization_code = data.get("authorization_code")
    code_verifier = data.get("code_verifier")
    if authorization_code and code_verifier:
        try:
            tokens = chatgpt_subscription.exchange_authorization_code(authorization_code, code_verifier)
            result = _provision_endpoint(tokens, pending["owner"])
        except Exception as exc:
            logger.exception("ChatGPT Subscription endpoint provisioning failed")
            raise chatgpt_subscription.to_http_exception(exc)
        return DeviceFlowPoll.authorized(result)

    err = data.get("error") or data.get("status")
    if err in ("authorization_pending", "pending", None):
        return DeviceFlowPoll.pending()
    if err == "slow_down":
        return DeviceFlowPoll.slow_down(int(data.get("interval") or 0) or None)
    if err in ("expired_token", "access_denied", "denied"):
        return DeviceFlowPoll.failed(err)
    return DeviceFlowPoll.pending(err or "unknown")


def setup_chatgpt_subscription_routes():
    router = create_device_flow_router(
        prefix="/api/chatgpt-subscription",
        tags=["chatgpt-subscription"],
        store=_DEVICE_FLOW_STORE,
        start_flow=_start_device_flow,
        poll_flow=_poll_device_flow,
    )

    @router.get("/codex-cli/status")
    def codex_cli_status(request: Request):
        require_admin(request)
        return chatgpt_subscription.codex_cli_auth_status()

    @router.post("/codex-cli/import")
    def import_codex_cli_auth(
        request: Request,
        auth_path: str = Form(""),
        set_default: str = Form("true"),
    ):
        require_admin(request)
        owner = get_current_user(request) or None
        try:
            tokens = chatgpt_subscription.read_codex_cli_chatgpt_tokens(auth_path.strip() or None)
            if chatgpt_subscription.access_token_is_expiring(tokens.get("access_token", "")):
                refreshed = chatgpt_subscription.refresh_oauth_tokens(
                    tokens.get("access_token", ""),
                    tokens.get("refresh_token", ""),
                )
                tokens.update(refreshed)
            force_default = str(set_default).strip().lower() not in {"0", "false", "no"}
            result = _provision_endpoint(
                tokens,
                owner,
                auth_label="ChatGPT Subscription (Codex CLI login)",
                endpoint_name="ChatGPT Subscription - Codex CLI",
                force_default=force_default,
            )
            result["source"] = "codex-cli"
            result["auth_path"] = tokens.get("source_path", "")
            return result
        except Exception as exc:
            logger.warning("Codex CLI ChatGPT Subscription import failed: %s", exc)
            raise chatgpt_subscription.to_http_exception(exc)

    return router
