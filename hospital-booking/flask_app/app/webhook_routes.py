"""Messaging webhooks and signed identity-link helpers (Phase 4.2 / 4.7).

Webhook payloads can prove channel ownership, not patient identity by
themselves. We only create channel_links when a signed webhook carries a
canonical/linkable patient_ref produced by an authenticated app/link flow.
"""

from __future__ import annotations

import re

import requests
from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import text

from shared_db import crypto, models
from shared_db.database import bind_tenant

from .services import messaging_links
# P3 dedup: signature/initData verification + ref parsing live ONLY in
# messaging_identity (single source of truth). Re-exported here so existing
# wh.* references (routes + tests) keep working.
from .services.messaging_identity import (  # noqa: F401
    InitDataValidationError,
    extract_patient_ref,
    validate_telegram_init_data,
    verify_line_signature,
    verify_telegram_secret,
)

webhook_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")

_START_SERVICE_POINT_RE = re.compile(r"^/start\s+sp_(\d+)$", re.IGNORECASE)


def _get_config(db):
    return db.query(models.MessagingConfig).order_by(models.MessagingConfig.id.asc()).first()


def _resolve_tenant_context(db, tenant_key: str) -> dict | None:
    row = db.execute(
        text("""
            SELECT schema_name, subdomain
            FROM public.hospitals
            WHERE schema_name = :tenant_key OR subdomain = :tenant_key
            LIMIT 1
        """),
        {"tenant_key": tenant_key},
    ).mappings().first()
    return dict(row) if row else None


def _bind_request_tenant(db, tenant_key: str) -> dict:
    tenant = _resolve_tenant_context(db, tenant_key)
    if not tenant:
        abort(404)
    schema_name = tenant["schema_name"]
    bind_tenant(db, schema_name)
    db.execute(text(f'SET search_path TO "{schema_name}", public'))
    return tenant


def _post_telegram_message(config, chat_id: str | int | None, text_message: str,
                           http_client=requests, reply_markup: dict | None = None) -> bool:
    if not chat_id or not getattr(config, "telegram_bot_token_enc", None):
        return False
    token = crypto.decrypt(config.telegram_bot_token_enc)
    try:
        response = http_client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text_message,
                **({"reply_markup": reply_markup} if reply_markup else {}),
            },
            timeout=10,
        )
    except requests.RequestException:
        return False
    if response.status_code >= 400:
        return False
    try:
        data = response.json()
    except ValueError:
        return False
    return bool(data.get("ok"))


def handle_line_events(db, payload: dict, config=None, http_client=requests) -> dict:
    """Process a (signature-verified) LINE webhook.

    SECURITY: a webhook proves channel ownership, NOT patient identity. We do NOT
    create channel_links from a patient_ref embedded in user-sent message/postback
    text — that ref is forgeable (anyone could send `patient_ref=patient:<id>` and
    bind their LINE account to another patient's notifications). Identity linking
    happens only via the verified Mini App flow (queue.channel_auth ->
    messaging_identity.link_line_identity, which verifies a LINE-issued ID token).
    """
    return {"linked": 0, "skipped": len(payload.get("events", []))}


def telegram_start_service_point_id(update: dict) -> int | None:
    message = update.get("message") or update.get("edited_message") or {}
    text_value = str(message.get("text") or "").strip()
    match = _START_SERVICE_POINT_RE.match(text_value)
    if not match:
        return None
    return int(match.group(1))


def _send_telegram_checkin_button(config, chat_id, service_point_id: int,
                                  public_base_url: str | None,
                                  subdomain: str | None,
                                  http_client=requests) -> bool:
    if not public_base_url:
        return False
    checkin_url = messaging_links.web_checkin_url(
        public_base_url,
        service_point_id,
        subdomain=subdomain,
    )
    return _post_telegram_message(
        config,
        chat_id,
        "กดปุ่มด้านล่างเพื่อเช็คอินกับ NudDee",
        http_client=http_client,
        reply_markup={
            "inline_keyboard": [[{
                "text": "เปิดหน้าเช็คอิน",
                "web_app": {"url": checkin_url},
            }]],
        },
    )


def handle_telegram_update(db, update: dict, config=None, http_client=requests,
                           public_base_url: str | None = None,
                           subdomain: str | None = None) -> dict:
    """Process a (secret-token-verified) Telegram webhook.

    SECURITY: like LINE, we do NOT link an identity from a forgeable patient_ref in
    free-text (e.g. `/start patient:<id>`). Identity linking happens only via the
    verified Mini App flow (initData -> queue.channel_auth ->
    messaging_identity.link_telegram_identity). The webhook only handles the
    `/start sp_<id>` deep link by sending an inline web_app button to the check-in
    page (which then opens the Mini App and links via the verified path).
    """
    config = config or _get_config(db)
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    service_point_id = telegram_start_service_point_id(update)
    if service_point_id is not None:
        _send_telegram_checkin_button(
            config,
            chat_id,
            service_point_id,
            public_base_url,
            subdomain,
            http_client=http_client,
        )
        db.commit()
        return {"linked": 0, "skipped": 1, "action": "checkin_button"}

    db.commit()
    return {"linked": 0, "skipped": 1}


@webhook_bp.route("/line/<tenant_key>", methods=["POST"])
def line_webhook(tenant_key):
    _bind_request_tenant(g.db, tenant_key)
    config = _get_config(g.db)
    body = request.get_data()
    secret = crypto.decrypt(config.line_channel_secret_enc) if config and config.line_channel_secret_enc else None
    if not verify_line_signature(secret, body, request.headers.get("X-Line-Signature")):
        abort(403)
    payload = request.get_json(silent=True) or {}
    return jsonify(handle_line_events(g.db, payload, config=config))


@webhook_bp.route("/telegram/<tenant_key>", methods=["POST"])
def telegram_webhook(tenant_key):
    tenant = _bind_request_tenant(g.db, tenant_key)
    config = _get_config(g.db)
    if not verify_telegram_secret(config, request.headers.get("X-Telegram-Bot-Api-Secret-Token")):
        abort(403)
    payload = request.get_json(silent=True) or {}
    return jsonify(handle_telegram_update(
        g.db,
        payload,
        config=config,
        public_base_url=request.url_root,
        subdomain=tenant.get("subdomain"),
    ))


@webhook_bp.route("/telegram/<tenant_key>/init-data", methods=["POST"])
def telegram_init_data(tenant_key):
    _bind_request_tenant(g.db, tenant_key)
    config = _get_config(g.db)
    payload = request.get_json(silent=True) or {}
    try:
        data = validate_telegram_init_data(config, payload.get("initData") or "")
    except InitDataValidationError as exc:
        return jsonify({"valid": False, "error": str(exc)}), 403
    return jsonify({"valid": True, "data": data})
