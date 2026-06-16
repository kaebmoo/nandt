import datetime

from shared_db import models
from flask_app.app.services import analytics_service as analytics

DT = datetime.datetime


def _entry(db, sp_id, day, qno, status, check_in, called=None, start=None, end=None, entry_class='walkin'):
    entry = models.QueueEntry(
        service_point_id=sp_id,
        session_date=day,
        patient_ref=f"phone:+6684000{qno:04d}",
        entry_class=entry_class,
        queue_number=qno,
        status=status,
        check_in_at=check_in,
        called_at=called,
        service_start_at=start,
        service_end_at=end,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_queue_summary_aggregates_wait_throughput_no_show_and_hourly(db, service_point):
    day = datetime.date(2026, 6, 15)
    _entry(
        db, service_point.id, day, 1, 'done',
        DT(2026, 6, 15, 8, 0),
        called=DT(2026, 6, 15, 8, 10),
        start=DT(2026, 6, 15, 8, 12),
        end=DT(2026, 6, 15, 8, 32),
        entry_class='appointment',
    )
    _entry(
        db, service_point.id, day, 2, 'done',
        DT(2026, 6, 15, 9, 0),
        called=DT(2026, 6, 15, 9, 20),
        start=DT(2026, 6, 15, 9, 22),
        end=DT(2026, 6, 15, 9, 52),
    )
    _entry(db, service_point.id, day, 3, 'no_show', DT(2026, 6, 15, 9, 30))
    _entry(db, service_point.id, day, 4, 'called', DT(2026, 6, 15, 9, 45))

    result = analytics.queue_summary(db, day, day)

    assert result['total_entries'] == 4
    assert result['throughput'] == 2
    assert result['no_show_count'] == 1
    assert result['terminal_entries'] == 3
    assert result['no_show_rate'] == 1 / 3
    assert result['avg_wait_minutes'] == 15
    assert result['avg_service_minutes'] == 25
    assert result['status_counts'] == {'done': 2, 'no_show': 1, 'called': 1}
    assert result['class_counts'] == {'appointment': 1, 'walkin': 3}
    by_hour = {row['hour']: row['count'] for row in result['hourly_checkins']}
    assert by_hour['08:00'] == 1
    assert by_hour['09:00'] == 3


def test_message_cost_summary_groups_by_channel_event_and_status(db):
    day = datetime.date(2026, 6, 15)
    rows = [
        models.NotificationLog(
            patient_ref='patient:1', event_type='queue_turn', channel='telegram',
            cost_units=0, status='sent', sent_at=DT(2026, 6, 15, 8, 0),
        ),
        models.NotificationLog(
            patient_ref='patient:2', event_type='queue_turn', channel='line_push',
            cost_units=1, status='sent', sent_at=DT(2026, 6, 15, 8, 1),
        ),
        models.NotificationLog(
            patient_ref='patient:3', event_type='reminder', channel='line_push',
            cost_units=1, status='failed', sent_at=DT(2026, 6, 15, 8, 2),
        ),
    ]
    db.add_all(rows)
    db.commit()

    result = analytics.message_cost_summary(db, day, day)

    assert result['total_notifications'] == 3
    assert result['total_cost_units'] == 1
    assert result['sent_cost_units'] == 1
    assert result['attempted_cost_units'] == 2
    assert result['failed_cost_units'] == 1
    assert result['status_counts'] == {'sent': 2, 'failed': 1}
    assert result['by_channel']['telegram'] == {
        'count': 1,
        'sent_count': 1,
        'failed_count': 0,
        'cost_units': 0,
        'sent_cost_units': 0,
        'attempted_cost_units': 0,
        'failed_cost_units': 0,
    }
    assert result['by_channel']['line_push'] == {
        'count': 2,
        'sent_count': 1,
        'failed_count': 1,
        'cost_units': 1,
        'sent_cost_units': 1,
        'attempted_cost_units': 2,
        'failed_cost_units': 1,
    }
    assert result['by_event']['queue_turn'] == {
        'count': 2,
        'sent_count': 2,
        'failed_count': 0,
        'cost_units': 1,
        'sent_cost_units': 1,
        'attempted_cost_units': 1,
        'failed_cost_units': 0,
    }
    assert result['by_event']['reminder'] == {
        'count': 1,
        'sent_count': 0,
        'failed_count': 1,
        'cost_units': 0,
        'sent_cost_units': 0,
        'attempted_cost_units': 1,
        'failed_cost_units': 1,
    }
