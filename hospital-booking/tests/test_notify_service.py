import datetime
import threading
import time
from collections import Counter

import pytest

from shared_db import crypto
from shared_db import models
from flask_app.app.services import notify_service as ns

DT = datetime.datetime


def _config(db, priority=None, reminder_enabled=True, line_token=True,
            line_status='active', telegram_status='active', pwa_status='active'):
    cfg = models.MessagingConfig(
        line_channel_token_enc='encrypted-token' if line_token else None,
        line_status=line_status,
        telegram_bot_token_enc='encrypted-telegram',
        telegram_status=telegram_status,
        pwa_status=pwa_status,
        channel_priority=priority or ['telegram', 'pwa', 'line_push'],
        reminder_enabled=reminder_enabled,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


def _link(db, patient_ref, channel, external_id=None):
    link = models.ChannelLink(
        patient_ref=patient_ref,
        channel=channel,
        external_id=external_id or f"{channel}-{patient_ref}",
        is_active=True,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _logs(db, patient_ref):
    return (db.query(models.NotificationLog)
            .filter_by(patient_ref=patient_ref)
            .order_by(models.NotificationLog.id)
            .all())


def _queue_entry(db, service_point):
    entry = models.QueueEntry(
        service_point_id=service_point.id,
        session_date=datetime.date(2026, 6, 15),
        patient_ref='patient:1',
        entry_class='walkin',
        queue_number=1,
        status='called',
        check_in_at=DT(2026, 6, 15, 8, 50),
        called_at=DT(2026, 6, 15, 9, 0),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@pytest.fixture()
def messaging_key(monkeypatch):
    monkeypatch.setenv(crypto.ENV_KEY, crypto.generate_key())


def test_notify_prefers_telegram_free_before_line_push(db, service_point):
    _config(db, priority=['telegram', 'line_push'])
    _link(db, 'patient:1', 'telegram')
    _link(db, 'patient:1', 'line')
    entry = _queue_entry(db, service_point)
    calls = []

    result = ns.notify(
        db,
        'patient:1',
        'queue_turn',
        'critical',
        context={'queue_entry_id': entry.id},
        senders={'telegram': lambda **kwargs: calls.append(kwargs) or True},
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('telegram', 0, 'sent')
    assert len(calls) == 1
    log = _logs(db, 'patient:1')[0]
    assert log.channel == 'telegram'
    assert log.cost_units == 0
    assert log.status == 'sent'
    assert log.queue_entry_id == entry.id


def test_notify_line_async_critical_costs_one_when_only_line_available(db):
    _config(db, priority=['telegram', 'pwa', 'line_push'])
    _link(db, 'patient:2', 'line')

    result = ns.notify(
        db,
        'patient:2',
        'queue_turn',
        'critical',
        senders={'line_push': lambda **kwargs: True},
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('line_push', 1, 'sent')
    log = _logs(db, 'patient:2')[0]
    assert log.channel == 'line_push'
    assert log.cost_units == 1
    assert log.status == 'sent'


def test_notify_skips_async_push_without_linked_identity(db):
    _config(db, priority=['telegram', 'line_push'])
    calls = []

    result = ns.notify(
        db,
        'patient:77',
        'queue_turn',
        'critical',
        senders={
            'telegram': lambda **kwargs: calls.append(kwargs) or True,
            'line_push': lambda **kwargs: calls.append(kwargs) or True,
        },
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('pull', 0, 'skipped', 'no_linked_identity')
    assert calls == []
    log = _logs(db, 'patient:77')[0]
    assert log.channel == 'pull'
    assert log.status == 'skipped'
    assert log.error == 'no_linked_identity'


def test_notify_skips_noncanonical_patient_ref_without_logging_name(db):
    _config(db, priority=['telegram'])

    result = ns.notify(
        db,
        'สมชาย ใจดี',
        'queue_turn',
        'critical',
        senders={'telegram': lambda **kwargs: True},
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('pull', 0, 'skipped', 'no_linked_identity')
    log = db.query(models.NotificationLog).one()
    assert log.patient_ref is None
    assert log.error == 'no_linked_identity'


def test_notify_falls_back_after_failed_channel(db):
    _config(db, priority=['telegram', 'pwa', 'line_push'])
    _link(db, 'patient:3', 'telegram')
    _link(db, 'patient:3', 'pwa')

    result = ns.notify(
        db,
        'patient:3',
        'queue_near',
        'critical',
        senders={
            'telegram': lambda **kwargs: False,
            'pwa': lambda **kwargs: True,
        },
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('pwa', 0, 'sent')
    logs = _logs(db, 'patient:3')
    assert [(l.channel, l.status, l.cost_units) for l in logs] == [
        ('telegram', 'failed', 0),
        ('pwa', 'sent', 0),
    ]


def test_notify_default_pwa_sender_uses_webpush(db, messaging_key, monkeypatch):
    cfg = models.MessagingConfig(
        pwa_status='active',
        pwa_vapid_public_key='public-key',
        pwa_vapid_private_key_enc=crypto.encrypt('private-key'),
        channel_priority=['pwa'],
    )
    db.add(cfg)
    db.commit()
    link = models.ChannelLink(
        patient_ref='patient:10',
        channel='pwa',
        external_id='https://push.example/sub/10',
        is_active=True,
        raw_profile={'endpoint': 'https://push.example/sub/10', 'keys': {'p256dh': 'k', 'auth': 'a'}},
    )
    db.add(link)
    db.commit()
    calls = []

    def fake_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(ns, '_webpush', fake_webpush)

    result = ns.notify(
        db,
        'patient:10',
        'queue_turn',
        'critical',
        context={'queue_number': 10, 'url': '/queue/ticket/10'},
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('pwa', 0, 'sent')
    assert calls[0]['subscription_info'] == link.raw_profile
    assert calls[0]['vapid_private_key'] == 'private-key'
    assert calls[0]['vapid_claims'] == {'sub': 'mailto:noreply@nuddee.com'}
    assert '"url": "/queue/ticket/10"' in calls[0]['data']


def test_notify_uses_only_active_channel_statuses(db):
    _config(db, priority=['telegram', 'line_push'], telegram_status='disabled', line_status='active')
    _link(db, 'patient:8', 'telegram')
    _link(db, 'patient:8', 'line')
    calls = []

    result = ns.notify(
        db,
        'patient:8',
        'queue_turn',
        'critical',
        senders={
            'telegram': lambda **kwargs: calls.append('telegram') or True,
            'line_push': lambda **kwargs: calls.append('line_push') or True,
        },
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('line_push', 1, 'sent')
    assert calls == ['line_push']
    log = _logs(db, 'patient:8')[0]
    assert log.channel == 'line_push'


def test_notify_low_reminder_skips_when_disabled(db):
    _config(db, reminder_enabled=False)
    _link(db, 'patient:4', 'telegram')

    result = ns.notify(
        db,
        'patient:4',
        'reminder',
        'low',
        senders={'telegram': lambda **kwargs: True},
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('pull', 0, 'skipped', 'notification_disabled')
    log = _logs(db, 'patient:4')[0]
    assert log.channel == 'pull'
    assert log.status == 'skipped'
    assert log.error == 'notification_disabled'


def test_notify_dedupes_recent_sent_event(db):
    _config(db)
    _link(db, 'patient:5', 'telegram')
    now = DT(2026, 6, 15, 9, 0)

    first = ns.notify(
        db,
        'patient:5',
        'queue_turn',
        'critical',
        senders={'telegram': lambda **kwargs: True},
        now=now,
    )
    second = ns.notify(
        db,
        'patient:5',
        'queue_turn',
        'critical',
        senders={'telegram': lambda **kwargs: True},
        now=now + datetime.timedelta(minutes=2),
    )

    assert first == ns.NotificationResult('telegram', 0, 'sent')
    assert second == ns.NotificationResult('pull', 0, 'skipped', 'duplicate_recent_notification')
    logs = _logs(db, 'patient:5')
    assert [(l.channel, l.status, l.error) for l in logs] == [
        ('telegram', 'sent', None),
        ('pull', 'skipped', 'duplicate_recent_notification'),
    ]


def test_notify_dedupe_lock_prevents_concurrent_double_push(make_session):
    s0 = make_session()
    _config(s0, priority=['line_push'])
    _link(s0, 'patient:99', 'line')
    s0.close()

    n_threads = 8
    barrier = threading.Barrier(n_threads)
    calls = []
    calls_lock = threading.Lock()
    results = [None] * n_threads
    errors = [None] * n_threads

    def sender(**kwargs):
        with calls_lock:
            calls.append(kwargs['patient_ref'])
        time.sleep(0.05)
        return True

    def worker(i):
        s = make_session()
        try:
            barrier.wait(timeout=10)
            results[i] = ns.notify(
                s,
                'patient:99',
                'queue_turn',
                'critical',
                senders={'line_push': sender},
                now=DT(2026, 6, 15, 9, 0),
            )
        except Exception as ex:  # noqa: BLE001
            errors[i] = repr(ex)
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(e is None for e in errors), f"errors: {errors}"
    assert len(calls) == 1
    assert Counter(results) == Counter({
        ns.NotificationResult('line_push', 1, 'sent'): 1,
        ns.NotificationResult('pull', 0, 'skipped', 'duplicate_recent_notification'): n_threads - 1,
    })

    s = make_session()
    logs = _logs(s, 'patient:99')
    s.close()
    assert Counter((l.channel, l.status, l.error) for l in logs) == Counter({
        ('line_push', 'sent', None): 1,
        ('pull', 'skipped', 'duplicate_recent_notification'): n_threads - 1,
    })


def test_notify_uses_line_reply_free_with_reply_token(db):
    _config(db)

    result = ns.notify(
        db,
        'patient:6',
        'checkin_confirm',
        'normal',
        reply_token='reply-token',
        senders={'line_reply': lambda **kwargs: True},
        now=DT(2026, 6, 15, 9, 0),
    )

    assert result == ns.NotificationResult('line_reply', 0, 'sent')
    log = _logs(db, 'patient:6')[0]
    assert log.channel == 'line_reply'
    assert log.cost_units == 0
