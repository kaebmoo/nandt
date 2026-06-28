"""Queue-call audio (Patch 21 §14): concatenative WAV playlist.

Flask-first: the server (call_next) decides WHO is called; the display only plays
an ordered list of clip files (display-only). Two tenant knobs:
  1. clip library — per-schema folder of .wav files (static/queue_audio/<schema>/),
     falling back to static/queue_audio/_default/ (Thai set shipped).
  2. template — ordered token list, e.g. ["call_prefix","{queue}","room_prefix","{room}"].

literal token -> "<token>.wav"; placeholder {queue}/{room} -> "<full>.wav" if recorded,
else fallback to reading each character ("355" -> 3.wav 5.wav 5.wav). Change the
spoken phrasing by editing the template + dropping WAVs — never the code.
"""

import os
import re

# default Thai set -> "เชิญหมายเลข {queue} ที่ห้อง {room}"
DEFAULT_TEMPLATE = ["call_prefix", "{queue}", "room_prefix", "{room}"]
DEFAULT_AUDIO_CONFIG = {"enabled": True, "template": DEFAULT_TEMPLATE, "volume": 1.0, "repeat": 1}

_PLACEHOLDER_RE = re.compile(r"^\{(\w+)\}$")
_CLIP_NAME_RE = re.compile(r"^[\w-]+$")   # clip basenames only; rejects path traversal
_CLIP_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "queue_audio")
_DEFAULT_DIR = "_default"


def build_playlist(template, values, available) -> list[str]:
    """Pure core: ordered clip filenames (.wav) from template + values + available set.

    `available` is a set of clip basenames (no extension). Missing literals/placeholders
    are skipped silently so a partial clip library degrades instead of erroring.
    """
    out = []
    for token in template or []:
        match = _PLACEHOLDER_RE.match(str(token))
        if match:
            value = str(values.get(match.group(1), "")).strip()
            if not value:
                continue
            if value in available:               # full clip recorded -> use it
                out.append(value + ".wav")
            else:                                # fallback: read each character
                out.extend(ch + ".wav" for ch in value if ch in available)
        elif str(token) in available:
            out.append(str(token) + ".wav")
    return out


def _tenant_dir(schema):
    return os.path.join(_CLIP_ROOT, schema) if schema else None


def available_clips(schema) -> set[str]:
    """Clip basenames available to this tenant (tenant folder ∪ shipped _default)."""
    names = set()
    for directory in (os.path.join(_CLIP_ROOT, _DEFAULT_DIR), _tenant_dir(schema)):
        if directory and os.path.isdir(directory):
            names.update(fn[:-4] for fn in os.listdir(directory) if fn.endswith(".wav"))
    return names


def clip_url(schema, filename):
    """Static URL for a clip — tenant file if present, else _default. None if name unsafe."""
    from flask import url_for
    base = filename[:-4] if str(filename).endswith(".wav") else str(filename)
    if not _CLIP_NAME_RE.match(base):
        return None
    tenant_dir = _tenant_dir(schema)
    if tenant_dir and os.path.isfile(os.path.join(tenant_dir, base + ".wav")):
        rel = f"queue_audio/{schema}/{base}.wav"
    else:
        rel = f"queue_audio/{_DEFAULT_DIR}/{base}.wav"
    return url_for("static", filename=rel)


def _coerce(value, cast, default):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def get_audio_config(messaging_config) -> dict:
    """Merge tenant audio_config (JSONB) over defaults; always returns a usable template.

    volume/repeat are coerced to numbers — a typo in the tenant JSONB (e.g. volume='high')
    must not 500 the public display.
    """
    cfg = dict(DEFAULT_AUDIO_CONFIG)
    raw = getattr(messaging_config, "audio_config", None) if messaging_config else None
    if isinstance(raw, dict):
        cfg.update({k: v for k, v in raw.items() if v is not None})
    if not cfg.get("template"):
        cfg["template"] = DEFAULT_TEMPLATE
    cfg["volume"] = _coerce(cfg.get("volume"), float, 1.0)
    cfg["repeat"] = _coerce(cfg.get("repeat"), int, 1)
    return cfg


def room_value(service_point) -> str:
    """{room} value: digits in the name if any ('ห้อง 13' -> '13'), else the full name
    (tenant records a '<name>.wav' clip to have a non-numeric room spoken)."""
    name = (getattr(service_point, "name", "") or "").strip()
    digits = re.sub(r"\D", "", name)
    return digits or name


def playlist_for(schema, service_point, queue_number, messaging_config) -> list[str]:
    """Resolve clip URLs to announce one called entry. [] when audio is off (tenant or room)."""
    cfg = get_audio_config(messaging_config)
    if not cfg.get("enabled"):
        return []
    room_cfg = (cfg.get("rooms") or {}).get(str(getattr(service_point, "id", "")))
    if room_cfg is not None and room_cfg.get("enabled") is False:
        return []
    names = build_playlist(
        cfg["template"],
        {"queue": str(queue_number), "room": room_value(service_point)},
        available_clips(schema),
    )
    return [u for u in (clip_url(schema, n) for n in names) if u]
