"""Queue and messaging analytics (Phase 5).

Business calculations stay in Python; templates only render precomputed values.
"""

import datetime
from collections import Counter, defaultdict

from shared_db import models


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
