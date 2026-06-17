import datetime
import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from flask_app.app.services import messaging_identity as mi
from shared_db import crypto, models


@pytest.fixture()
def messaging_key(monkeypatch):
    monkeypatch.setenv(crypto.ENV_KEY, crypto.generate_key())


class FakeLineVerifyHttp:
    def __init__(self, claims, status_code=200):
        self.claims = claims
        self.status_code = status_code
        self.calls = []

    def post(self, url, data, timeout):
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        claims = self.claims
        status_code = self.status_code
        return type("Response", (), {
            "status_code": status_code,
            "json": lambda self: claims,
        })()


def _init_data(token, params):
    data_check_string = "\n".join(f"{key}={params[key]}" for key in sorted(params))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    supplied_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": supplied_hash})


def _appointment(db):
    patient = models.Patient(name="Test Patient", phone_number="0812345678")
    db.add(patient)
    db.flush()
    appt = models.Appointment(
        patient_id=patient.id,
        booking_reference="VN-AUTH1",
        start_time=datetime.datetime(2026, 6, 17, 9, 0),
        end_time=datetime.datetime(2026, 6, 17, 9, 30),
    )
    db.add(appt)
    db.commit()
    return patient, appt


def test_line_id_token_links_verified_user_to_booking_patient(db, messaging_key):
    patient, _ = _appointment(db)
    cfg = models.MessagingConfig(line_login_channel_id="line-login-123")
    db.add(cfg)
    db.commit()
    http = FakeLineVerifyHttp({
        "aud": "line-login-123",
        "sub": "UlineUser",
        "name": "LINE User",
    })

    link = mi.link_line_identity(
        db,
        config=cfg,
        id_token="opaque-id-token",
        booking_reference="VN-AUTH1",
        http_client=http,
    )

    assert http.calls[0]["url"] == "https://api.line.me/oauth2/v2.1/verify"
    assert http.calls[0]["data"] == {
        "id_token": "opaque-id-token",
        "client_id": "line-login-123",
    }
    assert link.patient_ref == f"patient:{patient.id}"
    assert link.channel == "line"
    assert link.external_id == "UlineUser"
    assert link.raw_profile == {"source": "liff_id_token", "name": "LINE User"}


def test_line_id_token_audience_mismatch_does_not_link(db, messaging_key):
    _appointment(db)
    cfg = models.MessagingConfig(line_login_channel_id="line-login-123")
    db.add(cfg)
    db.commit()
    http = FakeLineVerifyHttp({"aud": "wrong-channel", "sub": "UlineUser"})

    with pytest.raises(mi.LineIdTokenError, match="audience_mismatch"):
        mi.link_line_identity(
            db,
            config=cfg,
            id_token="opaque-id-token",
            booking_reference="VN-AUTH1",
            http_client=http,
        )

    db.rollback()
    assert db.query(models.ChannelLink).count() == 0


def test_telegram_init_data_links_verified_user_to_booking_patient(db, messaging_key):
    patient, _ = _appointment(db)
    token = "123456:telegram-token"
    cfg = models.MessagingConfig(
        telegram_bot_token_enc=crypto.encrypt(token),
        telegram_status="active",
    )
    db.add(cfg)
    db.commit()
    now = int(datetime.datetime(2026, 6, 17, tzinfo=datetime.timezone.utc).timestamp())
    user = json.dumps({"id": 9001, "username": "nuddee_user"}, separators=(",", ":"))
    init_data = _init_data(token, {
        "auth_date": str(now),
        "user": user,
    })

    link = mi.link_telegram_identity(
        db,
        config=cfg,
        init_data=init_data,
        booking_reference="VN-AUTH1",
        now=now,
    )

    assert link.patient_ref == f"patient:{patient.id}"
    assert link.channel == "telegram"
    assert link.external_id == "9001"
    assert link.raw_profile == {
        "source": "telegram_init_data",
        "username": "nuddee_user",
    }


def test_telegram_init_data_phone_only_rejected_without_booking(db, messaging_key):
    """SECURITY: a self-asserted phone (no booking_reference) must NOT establish identity."""
    token = "123456:telegram-token"
    cfg = models.MessagingConfig(
        telegram_bot_token_enc=crypto.encrypt(token),
        telegram_status="active",
    )
    db.add(cfg)
    db.commit()
    now = int(datetime.datetime(2026, 6, 17, tzinfo=datetime.timezone.utc).timestamp())
    user = json.dumps({"id": 9001, "username": "nuddee_user"}, separators=(",", ":"))
    init_data = _init_data(token, {"auth_date": str(now), "user": user})

    with pytest.raises(mi.ChannelIdentityError, match="booking_reference_required"):
        mi.link_telegram_identity(db, config=cfg, init_data=init_data,
                                  patient_phone="081-234-5678", now=now)
    db.rollback()
    assert db.query(models.ChannelLink).count() == 0


def test_pwa_subscription_links_with_booking_reference(db):
    patient, _ = _appointment(db)
    link = mi.link_pwa_subscription(
        db,
        subscription={"endpoint": "https://push.example/sub/1", "keys": {"p256dh": "k"}},
        booking_reference="VN-AUTH1",
    )

    assert link.patient_ref == f"patient:{patient.id}"
    assert link.channel == "pwa"
    assert link.external_id == "https://push.example/sub/1"
    assert link.raw_profile == {"endpoint": "https://push.example/sub/1", "keys": {"p256dh": "k"}}

    with pytest.raises(mi.ChannelIdentityError, match="pwa_endpoint_missing"):
        mi.link_pwa_subscription(db, subscription={}, booking_reference="VN-AUTH1")
