"""Notification dispatcher (§5.6 / Phase 4.1).

This layer chooses the cheapest available channel, records notification_log, and
keeps external transports injectable so LINE/Telegram/PWA integrations can be
added without changing queue/business logic.
"""

import datetime
import json
from dataclasses import dataclass

import requests
from sqlalchemy import text

from shared_db import crypto
from shared_db import models
from . import identity_service
from . import queue_service as qs

FREE_CHANNELS = {'telegram', 'pwa', 'line_reply', 'liff', 'pull'}
PAID_CHANNELS = {'line_push'}
DEFAULT_PRIORITY = ['telegram', 'pwa', 'line_push']
RESPONSIVE_EVENTS = {'booking_confirm', 'checkin_confirm'}


@dataclass(frozen=True)
class NotificationResult:
    channel: str
    cost_units: int
    status: str
    error: str | None = None


def _now():
    return qs._now()


def _get_config(db):
    return db.query(models.MessagingConfig).order_by(models.MessagingConfig.id.asc()).first()


def _priority(config):
    value = getattr(config, 'channel_priority', None)
    if not value:
        return DEFAULT_PRIORITY
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return DEFAULT_PRIORITY
    cleaned = [ch for ch in value if ch in ('telegram', 'pwa', 'line_push')]
    return cleaned or DEFAULT_PRIORITY


def _links_by_channel(db, patient_ref):
    links = (db.query(models.ChannelLink)
             .filter_by(patient_ref=patient_ref, is_active=True)
             .all())
    grouped = {}
    for link in links:
        grouped.setdefault(link.channel, []).append(link)
    return grouped


def _cost(channel):
    return 1 if channel in PAID_CHANNELS else 0


def _channel_link_key(channel):
    return 'line' if channel == 'line_push' else channel


def _channel_status_active(config, channel):
    if channel in ('line_push', 'line_reply'):
        return getattr(config, 'line_status', 'not_configured') == 'active'
    if channel == 'telegram':
        return getattr(config, 'telegram_status', 'not_configured') == 'active'
    if channel == 'pwa':
        return getattr(config, 'pwa_status', 'disabled') == 'active'
    return True


def _is_channel_available(channel, *, links, config, reply_token):
    if channel == 'line_reply':
        return (
            bool(reply_token)
            and _channel_status_active(config, channel)
            and bool(getattr(config, 'line_channel_token_enc', None))
        )
    key = _channel_link_key(channel)
    if key not in links:
        return False
    if not _channel_status_active(config, channel):
        return False
    if channel == 'line_push':
        return bool(getattr(config, 'line_channel_token_enc', None))
    if channel == 'telegram':
        return bool(getattr(config, 'telegram_bot_token_enc', None))
    return True


def _candidate_channels(config, event_type, urgency, reply_token):
    if reply_token and event_type in RESPONSIVE_EVENTS:
        return ['line_reply']
    if urgency == 'low' and event_type == 'reminder' and not getattr(config, 'reminder_enabled', False):
        return []
    return _priority(config)


def _requires_linked_identity(channels):
    return any(ch in ('telegram', 'pwa', 'line_push') for ch in channels)


def _recent_sent_exists(db, patient_ref, event_type, now, dedupe_minutes):
    cutoff = now - datetime.timedelta(minutes=dedupe_minutes)
    return (db.query(models.NotificationLog.id)
            .filter(models.NotificationLog.patient_ref == patient_ref,
                    models.NotificationLog.event_type == event_type,
                    models.NotificationLog.status == 'sent',
                    models.NotificationLog.sent_at >= cutoff)
            .first() is not None)


def _lock_dedupe_key(db, patient_ref, event_type):
    """Serialize dedupe check + send + log per tenant/patient/event."""
    db.execute(
        text("SELECT pg_advisory_xact_lock("
             "hashtextextended(current_schema() || ':notify:' || :patient_ref || ':' || :event_type, 0))"),
        {"patient_ref": patient_ref, "event_type": event_type},
    )


def _log(db, *, patient_ref, event_type, channel, cost_units, status,
         context=None, error=None, now=None):
    log = models.NotificationLog(
        queue_entry_id=(context or {}).get('queue_entry_id'),
        patient_ref=patient_ref,
        event_type=event_type,
        channel=channel,
        cost_units=cost_units,
        status=status,
        sent_at=now or _now(),
        error=error,
        log_metadata=context or {},
    )
    db.add(log)
    db.flush()
    return log


def _message_text(event_type, context):
    qno = (context or {}).get('queue_number')
    if event_type == 'queue_turn':
        return f"ถึงคิวหมายเลข {qno} แล้ว กรุณาเข้ารับบริการ" if qno else "ถึงคิวของคุณแล้ว กรุณาเข้ารับบริการ"
    if event_type == 'queue_near':
        return f"ใกล้ถึงคิวหมายเลข {qno} แล้ว กรุณาเตรียมตัว" if qno else "ใกล้ถึงคิวของคุณแล้ว กรุณาเตรียมตัว"
    if event_type == 'checkin_confirm':
        return f"เช็คอินสำเร็จ เลขคิวของคุณคือ {qno}" if qno else "เช็คอินสำเร็จ"
    if event_type == 'booking_confirm':
        return "ยืนยันการจองเรียบร้อยแล้ว"
    if event_type == 'reminder':
        return "แจ้งเตือนนัดหมายของคุณ"
    return "มีการแจ้งเตือนจาก NudDee"


def _post_json(url, *, headers=None, payload=None):
    try:
        response = requests.post(url, headers=headers or {}, json=payload or {}, timeout=10)
    except requests.RequestException:
        return None
    if response.status_code >= 400:
        return None
    try:
        return response.json()
    except ValueError:
        return {}


def _send_telegram(config, link, event_type, context):
    if link is None:
        return False
    token = crypto.decrypt(config.telegram_bot_token_enc)
    data = _post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        payload={
            "chat_id": link.external_id,
            "text": _message_text(event_type, context),
        },
    )
    return bool(data and data.get('ok'))


def _send_line_push(config, link, event_type, context):
    if link is None:
        return False
    token = crypto.decrypt(config.line_channel_token_enc)
    data = _post_json(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {token}"},
        payload={
            "to": link.external_id,
            "messages": [{"type": "text", "text": _message_text(event_type, context)}],
        },
    )
    return data is not None


def _send_line_reply(config, reply_token, event_type, context):
    if not reply_token:
        return False
    token = crypto.decrypt(config.line_channel_token_enc)
    data = _post_json(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {token}"},
        payload={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": _message_text(event_type, context)}],
        },
    )
    return data is not None


def _default_sender(channel=None, event_type=None, context=None, reply_token=None,
                    link=None, config=None, **kwargs):
    """Default transports for server-side async/sync messaging channels."""
    if channel == 'telegram':
        return _send_telegram(config, link, event_type, context)
    if channel == 'line_push':
        return _send_line_push(config, link, event_type, context)
    if channel == 'line_reply':
        return _send_line_reply(config, reply_token, event_type, context)
    # PWA and LIFF client-side sends are wired in their own channel phases.
    return False


def notify(db, patient_ref, event_type, urgency, context=None,
           reply_token=None, senders=None, now=None, dedupe_minutes=5) -> NotificationResult:
    """Choose channel, send, and write notification_log.

    urgency: critical | normal | low
    senders: optional mapping channel -> callable for transport. The callable
    receives patient_ref, event_type, context, reply_token, link, and config.
    """
    context = context or {}
    senders = senders or {}
    now = now or _now()
    canonical_ref = identity_service.canonicalize_patient_ref(patient_ref)
    log_ref = canonical_ref

    _lock_dedupe_key(db, canonical_ref or 'unlinked', event_type)
    if canonical_ref and _recent_sent_exists(db, canonical_ref, event_type, now, dedupe_minutes):
        _log(db, patient_ref=log_ref, event_type=event_type, channel='pull',
             cost_units=0, status='skipped', context=context,
             error='duplicate_recent_notification', now=now)
        db.commit()
        return NotificationResult('pull', 0, 'skipped', 'duplicate_recent_notification')

    config = _get_config(db)
    if config is None:
        _log(db, patient_ref=log_ref, event_type=event_type, channel='pull',
             cost_units=0, status='skipped', context=context,
             error='messaging_config_missing', now=now)
        db.commit()
        return NotificationResult('pull', 0, 'skipped', 'messaging_config_missing')

    candidates = _candidate_channels(config, event_type, urgency, reply_token)
    if not candidates:
        _log(db, patient_ref=log_ref, event_type=event_type, channel='pull',
             cost_units=0, status='skipped', context=context,
             error='notification_disabled', now=now)
        db.commit()
        return NotificationResult('pull', 0, 'skipped', 'notification_disabled')

    links = _links_by_channel(db, canonical_ref) if canonical_ref else {}
    if _requires_linked_identity(candidates) and not links:
        _log(db, patient_ref=log_ref, event_type=event_type, channel='pull',
             cost_units=0, status='skipped', context=context,
             error='no_linked_identity', now=now)
        db.commit()
        return NotificationResult('pull', 0, 'skipped', 'no_linked_identity')

    last_error = None
    for channel in candidates:
        if not _is_channel_available(channel, links=links, config=config, reply_token=reply_token):
            continue
        link_key = _channel_link_key(channel)
        link = (links.get(link_key) or [None])[0]
        sender = senders.get(channel, _default_sender)
        try:
            ok = bool(sender(
                channel=channel,
                patient_ref=canonical_ref,
                event_type=event_type,
                context=context,
                reply_token=reply_token,
                link=link,
                config=config,
            ))
        except Exception as exc:  # noqa: BLE001 - dispatcher logs failure and falls back
            ok = False
            last_error = str(exc)

        if ok:
            cost_units = _cost(channel)
            _log(db, patient_ref=log_ref, event_type=event_type, channel=channel,
                 cost_units=cost_units, status='sent', context=context, now=now)
            db.commit()
            return NotificationResult(channel, cost_units, 'sent')

        last_error = last_error or 'send_failed'
        _log(db, patient_ref=log_ref, event_type=event_type, channel=channel,
             cost_units=_cost(channel), status='failed', context=context,
             error=last_error, now=now)

    _log(db, patient_ref=log_ref, event_type=event_type, channel='pull',
         cost_units=0, status='skipped', context=context,
         error=last_error or 'no_available_channel', now=now)
    db.commit()
    return NotificationResult('pull', 0, 'skipped', last_error or 'no_available_channel')
