"""Telegram bot provisioning helper (Phase 4.6).

This module is token-driven and works for both ownership models:
saas-managed and tenant-BYO. It validates the bot token, registers webhook/menu
settings through Bot API, then stores token/secret encrypted at rest.
"""

from __future__ import annotations

import secrets
import string
import re
from urllib.parse import quote

import requests

from shared_db import crypto, models

ALLOWED_OWNERSHIPS = {"saas", "tenant"}
WEBHOOK_SECRET_ALPHABET = string.ascii_letters + string.digits + "_-"
DEFAULT_ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"]
DEFAULT_COMMANDS = [
    {"command": "book", "description": "จองนัด"},
    {"command": "checkin", "description": "เช็คอิน"},
    {"command": "queue", "description": "ดูคิวของฉัน"},
    {"command": "appointments", "description": "นัดของฉัน"},
]
_BOT_TOKEN_IN_URL_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")
_BARE_BOT_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])\d{5,}:[A-Za-z0-9_-]{10,}")


class TelegramProvisioningError(RuntimeError):
    """Provisioning failed without exposing the bot token."""


def generate_webhook_secret(length: int = 48) -> str:
    if length < 1 or length > 256:
        raise ValueError("Telegram webhook secret length must be 1..256")
    return "".join(secrets.choice(WEBHOOK_SECRET_ALPHABET) for _ in range(length))


def _bot_api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _safe_error(message: object) -> str:
    text = str(message or "telegram provisioning failed")
    text = _BOT_TOKEN_IN_URL_RE.sub("bot<redacted>", text)
    text = _BARE_BOT_TOKEN_RE.sub("<redacted>", text)
    return text[:500]


def _call_bot_api(http_client, token: str, method: str, payload: dict | None = None) -> dict:
    try:
        response = http_client.post(
            _bot_api_url(token, method),
            json=payload or {},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise TelegramProvisioningError("Telegram API request failed") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise TelegramProvisioningError("Telegram API returned non-JSON response") from exc

    if getattr(response, "status_code", 200) >= 400 or not data.get("ok"):
        raise TelegramProvisioningError(_safe_error(data.get("description") or response))
    result = data.get("result")
    return result if isinstance(result, dict) else {"value": result}


def _get_config(db) -> models.MessagingConfig:
    cfg = db.query(models.MessagingConfig).order_by(models.MessagingConfig.id.asc()).first()
    if cfg is None:
        cfg = models.MessagingConfig()
        db.add(cfg)
        db.flush()
    return cfg


def _mark_error(db, error: Exception) -> None:
    cfg = _get_config(db)
    cfg.telegram_status = "error"
    cfg.telegram_last_error = _safe_error(error)
    db.commit()


def _webhook_url(public_base_url: str, tenant_key: str) -> str:
    return f"{public_base_url.rstrip('/')}/webhooks/telegram/{quote(tenant_key, safe='')}"


def _default_web_app_url(public_base_url: str, tenant_key: str) -> str:
    return f"{public_base_url.rstrip('/')}/?tenant={quote(tenant_key, safe='')}"


def provision_telegram_bot(
    db,
    tenant_key: str,
    token: str,
    ownership: str,
    public_base_url: str,
    *,
    mini_app_short_name: str | None = None,
    web_app_url: str | None = None,
    webhook_secret: str | None = None,
    http_client=requests,
) -> dict:
    """Validate token, configure Telegram Bot API surfaces, and persist config.

    `tenant_key` is the route key used by the webhook URL. In this repo it should
    be the resolved tenant schema or another stable tenant identifier supplied by
    the caller; this helper does not reconstruct schema names from subdomains.
    """
    if ownership not in ALLOWED_OWNERSHIPS:
        raise ValueError("telegram_bot_ownership must be 'saas' or 'tenant'")
    if not tenant_key:
        raise ValueError("tenant_key is required")
    if not token:
        raise ValueError("telegram bot token is required")
    if not public_base_url:
        raise ValueError("public_base_url is required")

    secret = webhook_secret or generate_webhook_secret()
    if not all(ch in WEBHOOK_SECRET_ALPHABET for ch in secret):
        raise ValueError("Telegram webhook secret must use A-Z a-z 0-9 _ -")
    if not (1 <= len(secret) <= 256):
        raise ValueError("Telegram webhook secret length must be 1..256")

    try:
        me = _call_bot_api(http_client, token, "getMe")
        username = me.get("username")
        if not username:
            raise TelegramProvisioningError("Telegram getMe did not return bot username")

        webhook_url = _webhook_url(public_base_url, tenant_key)
        _call_bot_api(http_client, token, "setWebhook", {
            "url": webhook_url,
            "secret_token": secret,
            "allowed_updates": DEFAULT_ALLOWED_UPDATES,
        })
        menu_url = web_app_url or _default_web_app_url(public_base_url, tenant_key)
        _call_bot_api(http_client, token, "setChatMenuButton", {
            "menu_button": {
                "type": "web_app",
                "text": "เปิด NudDee",
                "web_app": {"url": menu_url},
            },
        })
        _call_bot_api(http_client, token, "setMyCommands", {
            "commands": DEFAULT_COMMANDS,
        })
    except Exception as exc:
        _mark_error(db, exc)
        if isinstance(exc, TelegramProvisioningError):
            raise
        raise TelegramProvisioningError(_safe_error(exc)) from exc

    cfg = _get_config(db)
    cfg.telegram_bot_token_enc = crypto.encrypt(token)
    cfg.telegram_bot_username = username
    cfg.telegram_bot_ownership = ownership
    cfg.telegram_webhook_secret_enc = crypto.encrypt(secret)
    cfg.telegram_mini_app_short_name = mini_app_short_name
    cfg.telegram_status = "active"
    cfg.telegram_last_error = None
    db.commit()

    return {
        "status": "active",
        "bot_username": username,
        "ownership": ownership,
        "webhook_url": webhook_url,
        "mini_app_short_name": mini_app_short_name,
    }
