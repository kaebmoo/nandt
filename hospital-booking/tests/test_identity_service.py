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


def test_mint_anon_ref_is_unique_urlsafe_token():
    a = ids.mint_anon_ref()
    b = ids.mint_anon_ref()
    assert a.startswith("anon:") and b.startswith("anon:")
    assert len(a[len("anon:"):]) >= 22
    assert a != b                                   # unique per visit


def test_canonicalize_accepts_anon_token_rejects_garbage():
    token = ids.mint_anon_ref()
    assert ids.canonicalize_patient_ref(token) == token   # pass-through, no PII normalization
    assert ids.canonicalize_patient_ref("anon:short") is None
    assert ids.canonicalize_patient_ref("anon:has spaces invalid") is None


def test_resolve_mints_anon_only_as_last_fallback():
    # patient id / phone still win — anon is the final fallback, not a shortcut
    assert ids.resolve_patient_ref(patient_id=7, allow_anon=True) == "patient:7"
    assert ids.resolve_patient_ref(phone="0812345678", allow_anon=True) == "phone:+66812345678"
    minted = ids.resolve_patient_ref(allow_anon=True)
    assert minted.startswith("anon:")
    assert ids.resolve_patient_ref() is None              # no allow_anon -> still None
