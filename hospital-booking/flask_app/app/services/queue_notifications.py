"""Async queue notification wiring (Phase 4.13).

Staff requests must not send critical push notifications synchronously. They
only enqueue small RQ jobs; the worker opens its own tenant-bound DB session and
delegates channel selection/dedupe/cost logging to notify_service.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text

from shared_db import models
from shared_db.database import SessionLocal, bind_tenant

from . import notify_service
from . import queue_service as qs
from .redis_connection import redis_manager

logger = logging.getLogger(__name__)

QUEUE_NAME = "default"
JOB_PATH = "app.services.queue_notifications.notify_queue_event_job"
_VALID_SCHEMA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUEUE_TURN_LIVE_STATUSES = {"called", "in_service"}


def _entry_context(entry: models.QueueEntry) -> dict:
    return {
        "queue_entry_id": entry.id,
        "queue_number": entry.queue_number,
        "service_point_id": entry.service_point_id,
        "session_id": entry.session_id,
        "session_date": entry.session_date.isoformat() if entry.session_date else None,
        "status": entry.status,
    }


def enqueue_queue_event(
    schema_name: str | None,
    entry_id: int | None,
    event_type: str,
    urgency: str,
    context: dict | None = None,
    *,
    queue=None,
) -> bool:
    """Best-effort enqueue. Failure is logged but never breaks staff/patient flow."""
    if not schema_name or entry_id is None:
        logger.warning(
            "skip queue notification enqueue: schema or entry missing event_type=%s entry_id=%s",
            event_type,
            entry_id,
        )
        return False

    try:
        rq_queue = queue or redis_manager.get_queue(QUEUE_NAME)
        rq_queue.enqueue(
            JOB_PATH,
            schema_name,
            int(entry_id),
            event_type,
            urgency,
            context or {},
            job_timeout="2m",
        )
        logger.info(
            "enqueued queue notification schema=%s entry_id=%s event_type=%s urgency=%s",
            schema_name,
            entry_id,
            event_type,
            urgency,
        )
        return True
    except Exception:
        logger.exception(
            "queue notification enqueue failed schema=%s entry_id=%s event_type=%s",
            schema_name,
            entry_id,
            event_type,
        )
        return False


def enqueue_for_entry(schema_name: str | None, entry: models.QueueEntry,
                      event_type: str, urgency: str, *, url: str | None = None) -> bool:
    context = _entry_context(entry)
    if url:
        # PWA push click target (patient's signed ticket). Built at enqueue time in the
        # request, where url_helper knows subdomain vs host mode — the worker has no
        # request context. Without it _send_pwa falls back to "/" (wrong page).
        context["url"] = url
    return enqueue_queue_event(
        schema_name,
        entry.id,
        event_type,
        urgency,
        context=context,
    )


def enqueue_checkin_confirm(schema_name: str | None, entry: models.QueueEntry,
                            *, url: str | None = None) -> bool:
    return enqueue_for_entry(schema_name, entry, "checkin_confirm", "normal", url=url)


def enqueue_queue_turn(schema_name: str | None, entry: models.QueueEntry,
                       *, url: str | None = None) -> bool:
    return enqueue_for_entry(schema_name, entry, "queue_turn", "critical", url=url)


def enqueue_queue_near(schema_name: str | None, entry: models.QueueEntry,
                       *, url: str | None = None) -> bool:
    # Hook for the future near-turn detector; call_next currently wires queue_turn only.
    return enqueue_for_entry(schema_name, entry, "queue_near", "critical", url=url)


def _validate_schema_name(schema_name: str) -> None:
    if not _VALID_SCHEMA.match(schema_name or ""):
        raise ValueError(f"invalid tenant schema name: {schema_name!r}")


def _result_dict(result: notify_service.NotificationResult) -> dict:
    return {
        "channel": result.channel,
        "cost_units": result.cost_units,
        "status": result.status,
        "error": result.error,
    }


def _log_skipped(db, entry, event_type, context, reason):
    db.add(models.NotificationLog(
        queue_entry_id=entry.id,
        patient_ref=entry.patient_ref,
        event_type=event_type,
        channel="pull",
        cost_units=0,
        status="skipped",
        sent_at=qs._now(),
        error=reason,
        log_metadata=context,
    ))
    db.commit()
    return {
        "channel": "pull",
        "cost_units": 0,
        "status": "skipped",
        "error": reason,
    }


def notify_queue_event_job(schema_name: str, entry_id: int, event_type: str,
                           urgency: str = "critical", context: dict | None = None) -> dict:
    """RQ job entrypoint. Worker.py loads .env before resolving this dotted path."""
    _validate_schema_name(schema_name)
    context = context or {}
    db = SessionLocal()
    try:
        bind_tenant(db, schema_name)
        db.execute(text(f'SET search_path TO "{schema_name}", public'))

        entry = db.query(models.QueueEntry).filter_by(id=int(entry_id)).one_or_none()
        if entry is None:
            logger.warning(
                "queue notification entry missing schema=%s entry_id=%s event_type=%s",
                schema_name,
                entry_id,
                event_type,
            )
            return {
                "channel": "pull",
                "cost_units": 0,
                "status": "skipped",
                "error": "queue_entry_missing",
            }

        job_context = _entry_context(entry)
        job_context.update(context)

        if event_type == "queue_turn" and entry.status not in _QUEUE_TURN_LIVE_STATUSES:
            return _log_skipped(db, entry, event_type, job_context, "stale_queue_status")

        result = notify_service.notify(
            db,
            entry.patient_ref,
            event_type,
            urgency,
            context=job_context,
        )
        return _result_dict(result)
    finally:
        try:
            db.rollback()
            bind_tenant(db, None)
            db.execute(text("SET search_path TO public"))
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("failed to reset DB session after queue notification job")
        finally:
            db.close()
