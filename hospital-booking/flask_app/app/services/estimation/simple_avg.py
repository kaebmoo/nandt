"""Simple p80-based wait estimator (Phase 3, level 1-2)."""

import datetime
import math

from shared_db import models
from .. import queue_service as qs
from .base import EstimateResult

DEFAULT_SERVICE_MINUTES = 10.0


def _naive(dt):
    if dt is not None and getattr(dt, 'tzinfo', None) is not None:
        return dt.replace(tzinfo=None)
    return dt


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def rolling_service_time(db, service_point_id, now=None, pct=80, lookback_days=30, limit=200) -> float:
    """Return rolling service duration percentile in minutes for a service point."""
    now_n = _naive(now or qs._now())
    cutoff = now_n - datetime.timedelta(days=lookback_days)

    entries = (db.query(models.QueueEntry)
               .filter(models.QueueEntry.service_point_id == service_point_id,
                       models.QueueEntry.status == 'done',
                       models.QueueEntry.service_start_at.isnot(None),
                       models.QueueEntry.service_end_at.isnot(None),
                       models.QueueEntry.service_end_at >= cutoff)
               .order_by(models.QueueEntry.service_end_at.desc())
               .limit(limit)
               .all())

    durations = []
    for entry in entries:
        start = _naive(entry.service_start_at)
        end = _naive(entry.service_end_at)
        if start is None or end is None or end <= start:
            continue
        durations.append((end - start).total_seconds() / 60.0)

    value = _percentile(durations, pct / 100.0)
    return float(value) if value is not None else DEFAULT_SERVICE_MINUTES


class SimpleAverageEstimator:
    """Estimate wait from people ahead, parallel servers, and rolling p80 service time."""

    def __init__(self, db, tenant_config=None):
        self.db = db
        self.tenant_config = tenant_config

    def estimate(self, entry, now=None) -> EstimateResult:
        now = now or qs._now()
        people_ahead = qs.count_ahead(
            self.db,
            entry.service_point_id,
            entry.session_date,
            entry.queue_number,
        )
        service_point = entry.service_point
        if service_point is None:
            service_point = self.db.query(models.ServicePoint).filter_by(id=entry.service_point_id).one_or_none()
        servers = service_point.parallel_servers if service_point and service_point.parallel_servers else 1
        avg_minutes = rolling_service_time(self.db, entry.service_point_id, now=now, pct=80)
        wait = (people_ahead / max(int(servers), 1)) * avg_minutes
        return EstimateResult(
            wait_minutes=float(wait),
            people_ahead=people_ahead,
            method='simple_avg',
        )
