"""Queue and messaging analytics (Phase 5).

Business calculations stay in Python; templates only render precomputed values.
"""

import datetime
from collections import Counter, defaultdict

import requests

from shared_db import crypto, models

LINE_QUOTA_URL = "https://api.line.me/v2/bot/message/quota"
LINE_CONSUMPTION_URL = "https://api.line.me/v2/bot/message/quota/consumption"


def _date_bounds(date_from, date_to):
    if date_from > date_to:
        raise ValueError("date_from must be <= date_to")
    start_dt = datetime.datetime.combine(date_from, datetime.time.min)
    end_dt = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min)
    return start_dt, end_dt


def _minutes_between(start, end):
    if start is None or end is None or end <= start:
        return None
    return (end - start).total_seconds() / 60.0


def _avg(values):
    values = [v for v in values if v is not None]
    if not values:
        return 0.0
    return sum(values) / len(values)


def queue_summary(db, date_from, date_to, service_point_id=None):
    """Return queue KPIs for session_date in [date_from, date_to]."""
    query = db.query(models.QueueEntry).filter(
        models.QueueEntry.session_date >= date_from,
        models.QueueEntry.session_date <= date_to,
    )
    if service_point_id is not None:
        query = query.filter(models.QueueEntry.service_point_id == service_point_id)
    entries = query.all()

    wait_minutes = [_minutes_between(e.check_in_at, e.called_at) for e in entries]
    service_minutes = [_minutes_between(e.service_start_at, e.service_end_at) for e in entries]
    status_counts = Counter(e.status for e in entries)
    class_counts = Counter(e.entry_class for e in entries)
    hourly_checkins = Counter()
    for entry in entries:
        if entry.check_in_at is not None:
            hourly_checkins[entry.check_in_at.hour] += 1

    total = len(entries)
    done = status_counts.get('done', 0)
    no_show = status_counts.get('no_show', 0)
    terminal = done + no_show

    return {
        'date_from': date_from,
        'date_to': date_to,
        'total_entries': total,
        'throughput': done,
        'no_show_count': no_show,
        'terminal_entries': terminal,
        'no_show_rate': (no_show / terminal) if terminal else 0.0,
        'avg_wait_minutes': _avg(wait_minutes),
        'avg_service_minutes': _avg(service_minutes),
        'status_counts': dict(status_counts),
        'class_counts': dict(class_counts),
        'hourly_checkins': [
            {'hour': f"{hour:02d}:00", 'count': hourly_checkins.get(hour, 0)}
            for hour in range(24)
        ],
    }


def message_cost_summary(db, date_from, date_to):
    """Return notification cost and delivery summary for sent_at in [date_from, date_to]."""
    start_dt, end_dt = _date_bounds(date_from, date_to)
    logs = (db.query(models.NotificationLog)
            .filter(models.NotificationLog.sent_at >= start_dt,
                    models.NotificationLog.sent_at < end_dt)
            .all())

    def bucket():
        return {
            'count': 0,
            'sent_count': 0,
            'failed_count': 0,
            'cost_units': 0,              # real paid/sent cost (backward-compatible key)
            'sent_cost_units': 0,
            'attempted_cost_units': 0,
            'failed_cost_units': 0,
        }

    by_channel = defaultdict(bucket)
    by_event = defaultdict(bucket)
    status_counts = Counter()
    sent_cost = 0
    attempted_cost = 0
    failed_cost = 0
    for log in logs:
        cost = int(log.cost_units or 0)
        attempted_cost += cost
        status_counts[log.status] += 1
        for grouped in (by_channel[log.channel], by_event[log.event_type]):
            grouped['count'] += 1
            grouped['attempted_cost_units'] += cost
            if log.status == 'sent':
                grouped['sent_count'] += 1
                grouped['sent_cost_units'] += cost
                grouped['cost_units'] += cost
            elif log.status == 'failed':
                grouped['failed_count'] += 1
                grouped['failed_cost_units'] += cost
        if log.status == 'sent':
            sent_cost += cost
        elif log.status == 'failed':
            failed_cost += cost

    return {
        'date_from': date_from,
        'date_to': date_to,
        'total_notifications': len(logs),
        'total_cost_units': sent_cost,
        'sent_cost_units': sent_cost,
        'attempted_cost_units': attempted_cost,
        'failed_cost_units': failed_cost,
        'status_counts': dict(status_counts),
        'by_channel': dict(by_channel),
        'by_event': dict(by_event),
    }


def _line_quota_from_api(token, http_client=requests):
    """Pure HTTP+math half of line_message_quota (no DB) — easy to unit test.

    type='limited'  → {limit, used, remaining}
    type='none'     → unlimited plan, nothing to count
    4xx / bad data  → None (caller treats as 'unavailable')
    """
    headers = {"Authorization": f"Bearer {token}"}
    r1 = http_client.get(LINE_QUOTA_URL, headers=headers, timeout=10)
    if r1.status_code >= 400:
        return None
    quota = r1.json()
    if quota.get("type") != "limited":
        return {"type": quota.get("type") or "none", "limit": None, "used": None, "remaining": None}
    r2 = http_client.get(LINE_CONSUMPTION_URL, headers=headers, timeout=10)
    if r2.status_code >= 400:
        return None
    limit = int(quota.get("value") or 0)
    used = int(r2.json().get("totalUsage") or 0)
    return {"type": "limited", "limit": limit, "used": used, "remaining": max(0, limit - used)}


def line_message_quota(db, http_client=requests):
    """Live LINE push quota for this tenant (best-effort; None if not configured/down).

    Spent cost comes from notification_log (message_cost_summary); this adds the
    REMAINING side straight from LINE so staff see how close they are to the free
    cap. Any network/credential error returns None — analytics must never 500
    because LINE is unreachable.
    """
    config = db.query(models.MessagingConfig).order_by(models.MessagingConfig.id.asc()).first()
    if not config or getattr(config, 'line_status', None) != 'active':
        return None
    token_enc = getattr(config, 'line_channel_token_enc', None)
    if not token_enc:
        return None
    try:
        return _line_quota_from_api(crypto.decrypt(token_enc), http_client=http_client)
    except Exception:
        return None
