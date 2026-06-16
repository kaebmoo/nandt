import datetime

from shared_db import models
from flask_app.app.services.estimation import get_estimator
from flask_app.app.services.estimation.simple_avg import DEFAULT_SERVICE_MINUTES, rolling_service_time

DT = datetime.datetime


def _done_entry(db, sp_id, day, qno, start, minutes):
    entry = models.QueueEntry(
        service_point_id=sp_id,
        session_date=day,
        patient_ref=f"phone:+6685000{qno:04d}",
        entry_class='walkin',
        queue_number=qno,
        status='done',
        check_in_at=start - datetime.timedelta(minutes=5),
        called_at=start,
        service_start_at=start,
        service_end_at=start + datetime.timedelta(minutes=minutes),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _waiting_entry(db, sp_id, day, qno):
    entry = models.QueueEntry(
        service_point_id=sp_id,
        session_date=day,
        patient_ref=f"phone:+6685100{qno:04d}",
        entry_class='walkin',
        queue_number=qno,
        status='checked_in',
        check_in_at=DT(2026, 6, 15, 9, 0),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_factory_returns_simple_average_estimator(db):
    estimator = get_estimator(db)

    assert estimator.__class__.__name__ == "SimpleAverageEstimator"


def test_rolling_service_time_uses_p80_done_history(db, service_point):
    day = datetime.date(2026, 6, 15)
    base = DT(2026, 6, 15, 8, 0)
    for i, minutes in enumerate([10, 20, 30, 40, 50], start=1):
        _done_entry(db, service_point.id, day, i, base + datetime.timedelta(hours=i), minutes)

    value = rolling_service_time(db, service_point.id, now=DT(2026, 6, 16, 8, 0), pct=80)

    assert value == 42.0


def test_simple_average_estimate_counts_ahead_and_divides_by_servers(db, service_point):
    service_point.parallel_servers = 2
    db.commit()
    day = datetime.date(2026, 6, 15)
    base = DT(2026, 6, 15, 8, 0)
    for i, minutes in enumerate([10, 20, 30, 40, 50], start=1):
        _done_entry(db, service_point.id, day, i, base + datetime.timedelta(hours=i), minutes)

    _waiting_entry(db, service_point.id, day, 1)
    _waiting_entry(db, service_point.id, day, 2)
    target = _waiting_entry(db, service_point.id, day, 3)

    estimate = get_estimator(db).estimate(target, now=DT(2026, 6, 16, 8, 0))

    assert estimate.method == 'simple_avg'
    assert estimate.confidence == 'approx'
    assert estimate.people_ahead == 2
    assert estimate.wait_minutes == 42.0


def test_simple_average_estimate_uses_default_when_no_history(db, service_point):
    day = datetime.date(2026, 6, 15)
    _waiting_entry(db, service_point.id, day, 1)
    _waiting_entry(db, service_point.id, day, 2)
    target = _waiting_entry(db, service_point.id, day, 3)

    estimate = get_estimator(db).estimate(target, now=DT(2026, 6, 16, 8, 0))

    assert estimate.people_ahead == 2
    assert estimate.wait_minutes == 2 * DEFAULT_SERVICE_MINUTES
