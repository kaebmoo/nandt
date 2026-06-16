"""Canonical patient identity helpers for queue/messaging.

`patient_ref` is a join key, not display text. The only accepted forms are:
- patient:{id}
- phone:{normalized_phone}
"""

from __future__ import annotations

import re

PATIENT_PREFIX = "patient:"
PHONE_PREFIX = "phone:"
_MIN_PHONE_DIGITS = 8


class IdentityResolutionError(ValueError):
    """Raised when a queue/notification path cannot produce a canonical patient_ref."""


def normalize_phone(phone: str | None) -> str | None:
    """Normalize a phone number to a stable E.164-like value.

    Thai local numbers such as 0812345678 become +66812345678. Existing
    international forms keep their country code. Returns None for values that
    are too short to be a phone number, which prevents names like "w1" becoming
    accidental identity keys.
    """
    if phone is None:
        return None

    raw = str(phone).strip()
    if not raw:
        return None

    digits = re.sub(r"\D", "", raw)
    if len(digits) < _MIN_PHONE_DIGITS:
        return None

    if raw.startswith("+"):
        return f"+{digits}"
    if digits.startswith("00") and len(digits) > 2:
        return f"+{digits[2:]}"
    if digits.startswith("66"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+66{digits[1:]}"
    return f"+{digits}"


def patient_ref_for_patient_id(patient_id: int | str | None) -> str | None:
    if patient_id is None:
        return None
    try:
        value = int(patient_id)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return f"{PATIENT_PREFIX}{value}"


def patient_ref_for_phone(phone: str | None) -> str | None:
    normalized = normalize_phone(phone)
    return f"{PHONE_PREFIX}{normalized}" if normalized else None


def canonicalize_patient_ref(patient_ref: str | None) -> str | None:
    """Return a canonical patient_ref, or None if the input is not linkable."""
    if patient_ref is None:
        return None

    value = str(patient_ref).strip()
    if not value:
        return None

    if value.startswith(PATIENT_PREFIX):
        return patient_ref_for_patient_id(value[len(PATIENT_PREFIX):])
    if value.startswith(PHONE_PREFIX):
        return patient_ref_for_phone(value[len(PHONE_PREFIX):])
    return patient_ref_for_phone(value)


def is_canonical_patient_ref(patient_ref: str | None) -> bool:
    return canonicalize_patient_ref(patient_ref) == patient_ref


def resolve_patient_ref(*, appointment=None, patient=None, patient_id=None,
                        phone=None, fallback_ref=None, required=False) -> str | None:
    """Resolve a canonical patient_ref from known identity sources.

    Precedence is intentionally stable: verified patient id first, then phone.
    Names are never used as identity keys.
    """
    for candidate_id in (
        patient_id,
        getattr(patient, "id", None),
        getattr(appointment, "patient_id", None),
        getattr(getattr(appointment, "patient", None), "id", None),
    ):
        ref = patient_ref_for_patient_id(candidate_id)
        if ref:
            return ref

    for candidate_phone in (
        phone,
        getattr(patient, "phone_number", None),
        getattr(getattr(appointment, "patient", None), "phone_number", None),
        getattr(appointment, "guest_phone", None),
        fallback_ref,
    ):
        ref = canonicalize_patient_ref(candidate_phone)
        if ref:
            return ref

    if required:
        raise IdentityResolutionError("canonical patient_ref could not be resolved")
    return None
