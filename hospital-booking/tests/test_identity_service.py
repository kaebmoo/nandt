from shared_db import models
from flask_app.app.services import identity_service as ids


def test_patient_id_ref_wins_over_phone():
    appt = models.Appointment(patient_id=42, guest_phone="081-234-5678")

    assert ids.resolve_patient_ref(appointment=appt) == "patient:42"


def test_phone_ref_normalizes_thai_local_number():
    assert ids.patient_ref_for_phone("081-234-5678") == "phone:+66812345678"
    assert ids.canonicalize_patient_ref("phone:0812345678") == "phone:+66812345678"


def test_name_is_not_a_patient_ref():
    assert ids.canonicalize_patient_ref("สมชาย ใจดี") is None
    assert ids.resolve_patient_ref(fallback_ref="สมชาย ใจดี") is None


def test_required_resolution_raises_when_unlinkable():
    try:
        ids.resolve_patient_ref(fallback_ref="w1", required=True)
    except ids.IdentityResolutionError as exc:
        assert "canonical patient_ref" in str(exc)
    else:
        raise AssertionError("expected IdentityResolutionError")
