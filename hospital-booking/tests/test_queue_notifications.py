import datetime

import pytest

from shared_db import crypto
from shared_db import models
from flask_app.app.services import notify_service as ns
from flask_app.app.services import queue_notifications as qn


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return object()


class FakeResponse:
    status_code = 200

    def json(self):
        return {"ok": True, "result": {"message_id": 1}}


@pytest.fixture()
def messaging_key(monkeypatch):
    monkeypatch.setenv(crypto.ENV_KEY, crypto.generate_key())


def _config(db):
    cfg = models.MessagingConfig(
        telegram_bot_token_enc=crypto.encrypt("123456:telegram-token"),
        telegram_status="active",
        line_status="not_configured",
        pwa_status="disabled",
        channel_priority=["telegram", "line_push"],
    )
    db.add(cfg)
    db.commit()
    return cfg


def _link(db, patient_ref="patient:10"):
    link = models.ChannelLink(
        patient_ref=patient_ref,
        channel="telegram",
        external_id=f"chat-{patient_ref}",
        is_active=True,
    )
    db.add(link)
    db.commit()
    return link


def _entry(db, service_point, *, patient_ref="patient:10", status="called"):
    entry = models.QueueEntry(
        service_point_id=service_point.id,
        session_date=datetime.date(2026, 6, 16),
        patient_ref=patient_ref,
        entry_class="appointment",
        queue_number=7,
        status=status,
        check_in_at=datetime.datetime(2026, 6, 16, 8, 50),
        called_at=datetime.datetime(2026, 6, 16, 9, 0) if status == "called" else None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_enqueue_queue_event_uses_worker_dotted_path():
    fake = FakeQueue()

    ok = qn.enqueue_queue_event(
        "tenant_humnoi",
        123,
        "queue_turn",
        "critical",
        {"queue_number": 9},
        queue=fake,
    )

    assert ok is True
    assert len(fake.calls) == 1
    args, kwargs = fake.calls[0]
    assert args == (
        qn.JOB_PATH,
        "tenant_humnoi",
        123,
        "queue_turn",
        "critical",
        {"queue_number": 9},
    )
    assert kwargs == {"job_timeout": "2m"}


def test_notify_queue_event_job_sends_queue_turn_via_free_telegram(
    db, test_schema, service_point, messaging_key, monkeypatch
):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(ns.requests, "post", fake_post)
    _config(db)
    _link(db, "patient:10")
    entry = _entry(db, service_point, patient_ref="patient:10", status="called")

    result = qn.notify_queue_event_job(
        test_schema,
        entry.id,
        "queue_turn",
        "critical",
        {"source": "test"},
    )

    assert result == {
        "channel": "telegram",
        "cost_units": 0,
        "status": "sent",
        "error": None,
    }
    assert calls == [{
        "url": "https://api.telegram.org/bot123456:telegram-token/sendMessage",
        "headers": {},
        "json": {
            "chat_id": "chat-patient:10",
            "text": "ถึงคิวหมายเลข 7 แล้ว กรุณาเข้ารับบริการ",
        },
        "timeout": 10,
    }]
    db.expire_all()
    log = db.query(models.NotificationLog).filter_by(patient_ref="patient:10").one()
    assert log.event_type == "queue_turn"
    assert log.channel == "telegram"
    assert log.cost_units == 0
    assert log.status == "sent"
    assert log.queue_entry_id == entry.id
    assert log.log_metadata["queue_number"] == 7
    assert log.log_metadata["source"] == "test"


def test_notify_queue_turn_job_skips_stale_terminal_entry(db, test_schema, service_point, messaging_key):
    _config(db)
    _link(db, "patient:11")
    entry = _entry(db, service_point, patient_ref="patient:11", status="done")

    result = qn.notify_queue_event_job(test_schema, entry.id, "queue_turn", "critical")

    assert result == {
        "channel": "pull",
        "cost_units": 0,
        "status": "skipped",
        "error": "stale_queue_status",
    }
    db.expire_all()
    log = db.query(models.NotificationLog).filter_by(patient_ref="patient:11").one()
    assert log.event_type == "queue_turn"
    assert log.channel == "pull"
    assert log.status == "skipped"
    assert log.error == "stale_queue_status"
