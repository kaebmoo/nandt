import base64
import datetime
import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from shared_db import crypto, models
from flask_app.app import webhook_routes as wh


@pytest.fixture()
def messaging_key(monkeypatch):
    monkeypatch.setenv(crypto.ENV_KEY, crypto.generate_key())


def _config(db, *, line_secret="line-secret", telegram_secret="telegram-secret",
            telegram_token="123456:telegram-token"):
    cfg = models.MessagingConfig(
        line_channel_secret_enc=crypto.encrypt(line_secret),
        line_status="active",
        telegram_webhook_secret_enc=crypto.encrypt(telegram_secret),
        telegram_bot_token_enc=crypto.encrypt(telegram_token),
        telegram_status="active",
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def _line_signature(secret, body):
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _init_data(token, params):
    data_check_string = "\n".join(f"{key}={params[key]}" for key in sorted(params))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    supplied_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": supplied_hash})


class FakeTelegramReplyHttp:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return type("Response", (), {"status_code": 200, "json": lambda self: {"ok": True}})()


def test_line_signature_verify_accepts_only_matching_signature():
    body = b'{"events":[]}'
    sig = _line_signature("line-secret", body)

    assert wh.verify_line_signature("line-secret", body, sig) is True
    assert wh.verify_line_signature("line-secret", body, "bad") is False
    assert wh.verify_line_signature(None, body, sig) is False


def test_line_webhook_ignores_forgeable_free_text_ref(db, messaging_key):
    """SECURITY: a patient_ref in user-sent message text must NOT create a link.

    Anyone could send `patient_ref=patient:42` to the OA and bind their LINE
    account to another patient's notifications — webhook linking is removed;
    identity linking is only via the verified Mini App (channel-auth/LIFF).
    """
    cfg = _config(db)
    payload = {
        "events": [{
            "type": "message",
            "source": {"type": "user", "userId": "Uline123"},
            "message": {"type": "text", "text": "patient_ref=patient:42"},
        }]
    }

    result = wh.handle_line_events(db, payload, config=cfg)

    assert result == {"linked": 0, "skipped": 1}
    assert db.query(models.ChannelLink).count() == 0


def test_line_webhook_does_not_link_follow_without_patient_ref(db, messaging_key):
    cfg = _config(db)
    payload = {
        "events": [{
            "type": "follow",
            "source": {"type": "user", "userId": "Uline123"},
        }]
    }

    result = wh.handle_line_events(db, payload, config=cfg)

    assert result == {"linked": 0, "skipped": 1}
    assert db.query(models.ChannelLink).count() == 0


def test_telegram_secret_verify_and_free_text_ref_does_not_link(db, messaging_key):
    """SECURITY: secret-token verify works; a forgeable `/start patient:<id>` must
    NOT create a link nor send a confirmation reply (linking is Mini-App-only)."""
    cfg = _config(db)
    http = FakeTelegramReplyHttp()
    update = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": 9001, "type": "private"},
            "text": "/start patient:88",
        },
    }

    assert wh.verify_telegram_secret(cfg, "telegram-secret") is True
    assert wh.verify_telegram_secret(cfg, "wrong-secret") is False

    result = wh.handle_telegram_update(db, update, config=cfg, http_client=http)

    assert result == {"linked": 0, "skipped": 1}
    assert db.query(models.ChannelLink).count() == 0
    assert http.calls == []   # no "ผูกบัญชีแล้ว" confirmation for a forged ref


def test_telegram_start_service_point_sends_checkin_button_without_linking(db, messaging_key):
    cfg = _config(db)
    http = FakeTelegramReplyHttp()
    update = {
        "update_id": 2,
        "message": {
            "message_id": 11,
            "chat": {"id": 9002, "type": "private"},
            "text": "/start sp_7",
        },
    }

    result = wh.handle_telegram_update(
        db,
        update,
        config=cfg,
        http_client=http,
        public_base_url="https://humnoi.example.com/",
        subdomain="humnoi",
    )

    assert result == {"linked": 0, "skipped": 1, "action": "checkin_button"}
    assert db.query(models.ChannelLink).count() == 0
    assert len(http.calls) == 1
    assert http.calls[0]["json"]["chat_id"] == 9002
    assert http.calls[0]["json"]["reply_markup"] == {
        "inline_keyboard": [[{
            "text": "เปิดหน้าเช็คอิน",
            "web_app": {
                "url": "https://humnoi.example.com/queue/checkin/7?subdomain=humnoi",
            },
        }]],
    }


def test_extract_patient_ref_normalizes_phone_ref():
    assert wh.extract_patient_ref("patient_ref=phone:%2B66812345678") == "phone:+66812345678"
    assert wh.extract_patient_ref("สมชาย ใจดี") is None


def test_validate_telegram_init_data_accepts_valid_payload(db, messaging_key):
    cfg = _config(db, telegram_token="123456:telegram-token")
    now = int(datetime.datetime(2026, 6, 17, tzinfo=datetime.timezone.utc).timestamp())
    user = json.dumps({"id": 9001, "first_name": "Test"}, separators=(",", ":"))
    init_data = _init_data("123456:telegram-token", {
        "auth_date": str(now),
        "query_id": "AAE",
        "user": user,
    })

    data = wh.validate_telegram_init_data(cfg, init_data, now=now)

    assert data["auth_date"] == str(now)
    assert data["query_id"] == "AAE"
    assert data["user"] == {"id": 9001, "first_name": "Test"}


def test_validate_telegram_init_data_rejects_bad_hash_and_expired(db, messaging_key):
    cfg = _config(db, telegram_token="123456:telegram-token")
    now = int(datetime.datetime(2026, 6, 17, tzinfo=datetime.timezone.utc).timestamp())
    valid = _init_data("123456:telegram-token", {
        "auth_date": str(now),
        "query_id": "AAE",
    })

    with pytest.raises(wh.InitDataValidationError, match="hash invalid"):
        wh.validate_telegram_init_data(cfg, valid.replace("hash=", "hash=bad"), now=now)

    expired = _init_data("123456:telegram-token", {
        "auth_date": str(now - 301),
        "query_id": "AAE",
    })
    with pytest.raises(wh.InitDataValidationError, match="expired"):
        wh.validate_telegram_init_data(cfg, expired, now=now)
