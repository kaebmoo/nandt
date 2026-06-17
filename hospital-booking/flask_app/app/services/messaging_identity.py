"""Signed messaging identity helpers for LINE/Telegram/PWA.

Channel ownership alone is not a patient identity. These helpers only link a
channel to a canonical patient_ref after the channel proof is verified and the
patient_ref is resolved from server-side booking/phone data.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import re
from urllib.parse import parse_qs, parse_qsl, unquote_plus

import requests

from shared_db import crypto, models

from . import identity_service

_LINK_PREFIX_RE = re.compile(r"^(?:/start\s+|link[:=_-]?|ref[:=])(.+)$", re.IGNORECASE)


class InitDataValidationError(ValueError):
    """Telegram Mini App initData is missing, expired, or has an invalid hash."""


class LineIdTokenError(ValueError):
    """LINE LIFF ID token could not be verified by LINE."""


class ChannelIdentityError(ValueError):
    """The signed channel identity could not be linked to a patient_ref."""


def get_config(db):
    return db.query(models.MessagingConfig).order_by(models.MessagingConfig.id.asc()).first()


def _canonical_ref_from_value(value) -> str | None:
    if value is None:
        return None
    return identity_service.canonicalize_patient_ref(unquote_plus(str(value).strip()))


def extract_patient_ref(value) -> str | None:
    """Extract canonical patient_ref from query-like text or a direct ref token."""
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None

    match = _LINK_PREFIX_RE.match(text_value)
    if match:
        text_value = match.group(1).strip()

    if "?" in text_value:
        text_value = text_value.split("?", 1)[1]

    if "=" in text_value:
        params = parse_qs(text_value, keep_blank_values=False)
        for key in ("patient_ref", "ref"):
            if key in params and params[key]:
                ref = _canonical_ref_from_value(params[key][0])
                if ref:
                    return ref

    return _canonical_ref_from_value(text_value)


def upsert_channel_link(db, *, patient_ref: str | None, channel: str,
                        external_id: str | None, raw_profile: dict | None = None):
    canonical_ref = identity_service.canonicalize_patient_ref(patient_ref)
    if not canonical_ref or not external_id:
        return None
    link = (db.query(models.ChannelLink)
            .filter_by(channel=channel, external_id=str(external_id))
            .one_or_none())
    if link is None:
        link = models.ChannelLink(
            patient_ref=canonical_ref,
            channel=channel,
            external_id=str(external_id),
            is_active=True,
            raw_profile=raw_profile or {},
        )
        db.add(link)
    else:
        link.patient_ref = canonical_ref
        link.is_active = True
        link.raw_profile = raw_profile or {}
    db.flush()
    return link


def resolve_patient_ref_from_inputs(db, *, booking_reference: str | None = None,
                                    patient_phone: str | None = None) -> str:
    """Resolve patient_ref from a booking_reference (the identity proof).

    SECURITY: a self-asserted phone number is NOT proof of ownership — without an
    SMS/voice OTP anyone could claim another person's phone and hijack their queue
    notifications. (OTP via LINE/Telegram can't verify a phone: you'd already need a
    link to that person to deliver it — circular.) So identity MUST be established
    via the per-patient secret `booking_reference`; `patient_phone` is only a
    secondary hint to pick the ref from the resolved appointment, never a standalone
    identity. Walk-ins (no booking_reference) link via their ticket context instead.
    """
    booking_reference = (booking_reference or "").strip()
    patient_phone = (patient_phone or "").strip()

    if not booking_reference:
        raise ChannelIdentityError("booking_reference_required")

    appointment = (db.query(models.Appointment)
                   .filter_by(booking_reference=booking_reference)
                   .one_or_none())
    if appointment is None:
        raise ChannelIdentityError("booking_reference_not_found")
    patient_ref = identity_service.resolve_patient_ref(
        appointment=appointment,
        phone=patient_phone,
        required=False,
    )

    if not patient_ref:
        raise ChannelIdentityError("patient_ref_required")
    return patient_ref


def verify_line_signature(secret: str | None, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def verify_line_id_token(config, id_token: str | None, http_client=requests) -> dict:
    """Verify a LIFF ID token via LINE and return trusted claims.

    The ID token itself is never logged or persisted. LINE's verify endpoint
    performs signature validation; we still enforce `aud` against the tenant's
    Login channel id because Messaging channel id is not interchangeable here.
    """
    id_token = (id_token or "").strip()
    login_channel_id = getattr(config, "line_login_channel_id", None)
    if not id_token:
        raise LineIdTokenError("id_token_missing")
    if not login_channel_id:
        raise LineIdTokenError("line_login_channel_missing")

    try:
        response = http_client.post(
            "https://api.line.me/oauth2/v2.1/verify",
            data={"id_token": id_token, "client_id": login_channel_id},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise LineIdTokenError("line_id_token_verify_failed") from exc

    if response.status_code >= 400:
        raise LineIdTokenError("line_id_token_invalid")

    try:
        claims = response.json()
    except ValueError as exc:
        raise LineIdTokenError("line_id_token_invalid") from exc

    if str(claims.get("aud") or "") != str(login_channel_id):
        raise LineIdTokenError("line_id_token_audience_mismatch")
    if not claims.get("sub"):
        raise LineIdTokenError("line_user_missing")
    return claims


def link_line_identity(db, *, config=None, id_token: str | None = None,
                       booking_reference: str | None = None,
                       patient_phone: str | None = None,
                       http_client=requests):
    config = config or get_config(db)
    claims = verify_line_id_token(config, id_token, http_client=http_client)
    patient_ref = resolve_patient_ref_from_inputs(
        db,
        booking_reference=booking_reference,
        patient_phone=patient_phone,
    )
    link = upsert_channel_link(
        db,
        patient_ref=patient_ref,
        channel="line",
        external_id=claims["sub"],
        raw_profile={"source": "liff_id_token", "name": claims.get("name")},
    )
    db.commit()
    return link


def verify_telegram_secret(config, header_secret: str | None) -> bool:
    if not config or not header_secret or not getattr(config, "telegram_webhook_secret_enc", None):
        return False
    expected = crypto.decrypt(config.telegram_webhook_secret_enc)
    return hmac.compare_digest(expected or "", header_secret)


def validate_telegram_init_data(config, init_data: str, *,
                                now: int | None = None, max_age_seconds: int = 300) -> dict:
    if not init_data:
        raise InitDataValidationError("initData missing")
    if not config or not getattr(config, "telegram_bot_token_enc", None):
        raise InitDataValidationError("telegram bot token missing")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    supplied_hash = pairs.pop("hash", None)
    if not supplied_hash:
        raise InitDataValidationError("hash missing")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataValidationError("auth_date invalid") from exc
    now_ts = int(now if now is not None else datetime.datetime.now(datetime.timezone.utc).timestamp())
    if auth_date <= 0 or now_ts - auth_date > max_age_seconds or auth_date - now_ts > 60:
        raise InitDataValidationError("initData expired")

    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    token = crypto.decrypt(config.telegram_bot_token_enc)
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, supplied_hash):
        raise InitDataValidationError("hash invalid")

    parsed = dict(pairs)
    if "user" in parsed:
        try:
            parsed["user"] = json.loads(parsed["user"])
        except json.JSONDecodeError as exc:
            raise InitDataValidationError("user JSON invalid") from exc
    return parsed


def link_telegram_identity(db, *, config=None, init_data: str | None = None,
                           booking_reference: str | None = None,
                           patient_phone: str | None = None,
                           now: int | None = None):
    config = config or get_config(db)
    data = validate_telegram_init_data(config, init_data or "", now=now)
    user = data.get("user") or {}
    telegram_user_id = user.get("id")
    if telegram_user_id is None:
        raise ChannelIdentityError("telegram_user_missing")

    patient_ref = resolve_patient_ref_from_inputs(
        db,
        booking_reference=booking_reference,
        patient_phone=patient_phone,
    )
    link = upsert_channel_link(
        db,
        patient_ref=patient_ref,
        channel="telegram",
        external_id=str(telegram_user_id),
        raw_profile={"source": "telegram_init_data", "username": user.get("username")},
    )
    db.commit()
    return link


def link_pwa_subscription(db, *, subscription: dict | None,
                          booking_reference: str | None = None,
                          patient_phone: str | None = None):
    subscription = subscription or {}
    endpoint = subscription.get("endpoint")
    if not endpoint:
        raise ChannelIdentityError("pwa_endpoint_missing")
    patient_ref = resolve_patient_ref_from_inputs(
        db,
        booking_reference=booking_reference,
        patient_phone=patient_phone,
    )
    link = upsert_channel_link(
        db,
        patient_ref=patient_ref,
        channel="pwa",
        external_id=endpoint,
        raw_profile=subscription,
    )
    db.commit()
    return link


def link_pwa_subscription_for_patient_ref(db, *, subscription: dict | None,
                                          patient_ref: str | None):
    subscription = subscription or {}
    endpoint = subscription.get("endpoint")
    if not endpoint:
        raise ChannelIdentityError("pwa_endpoint_missing")
    canonical_ref = identity_service.canonicalize_patient_ref(patient_ref)
    if not canonical_ref:
        raise ChannelIdentityError("patient_ref_required")
    link = upsert_channel_link(
        db,
        patient_ref=canonical_ref,
        channel="pwa",
        external_id=endpoint,
        raw_profile=subscription,
    )
    db.commit()
    return link
