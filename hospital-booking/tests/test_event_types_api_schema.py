import datetime

from fastapi_app.app.event_types import EventTypeCreate, EventTypeResponse, EventTypeUpdate
from shared_db import models


def test_event_type_create_defaults_requires_queue_false():
    payload = EventTypeCreate(
        name="นัดทั่วไป",
        duration_minutes=30,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
        max_advance_days=60,
        is_active=True,
    )

    assert payload.requires_queue is False


def test_event_type_update_accepts_requires_queue():
    payload = EventTypeUpdate(requires_queue=True)

    assert payload.model_dump(exclude_unset=True) == {'requires_queue': True}


def test_event_type_response_includes_requires_queue():
    et = models.EventType(
        id=1,
        name="บริการใช้คิว",
        slug="queue-service",
        description=None,
        duration_minutes=30,
        color="#6366f1",
        is_active=True,
        requires_queue=True,
        template_id=None,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
        max_bookings_per_day=None,
        min_notice_hours=4,
        max_advance_days=60,
        created_at=datetime.datetime(2026, 6, 14, 9, 0),
    )

    response = EventTypeResponse.model_validate(et)

    assert response.requires_queue is True
