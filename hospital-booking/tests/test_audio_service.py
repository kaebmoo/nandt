"""Queue-call audio playlist builder (Patch 21 §14) — pure, no DB/Flask."""

from flask_app.app.services import audio_service as audio

TEMPLATE = ["call_prefix", "{queue}", "room_prefix", "{room}"]
DIGITS = {str(i) for i in range(10)} | {"call_prefix", "room_prefix"}


def test_full_clip_used_when_recorded():
    available = DIGITS | {"355", "13"}
    out = audio.build_playlist(TEMPLATE, {"queue": "355", "room": "13"}, available)
    assert out == ["call_prefix.wav", "355.wav", "room_prefix.wav", "13.wav"]


def test_falls_back_to_per_digit_when_full_missing():
    out = audio.build_playlist(TEMPLATE, {"queue": "355", "room": "13"}, DIGITS)
    assert out == ["call_prefix.wav", "3.wav", "5.wav", "5.wav",
                   "room_prefix.wav", "1.wav", "3.wav"]


def test_missing_literal_and_empty_value_are_skipped():
    # no room value + room_prefix clip missing -> both dropped, queue still reads
    available = {str(i) for i in range(10)} | {"call_prefix"}
    out = audio.build_playlist(TEMPLATE, {"queue": "7", "room": ""}, available)
    assert out == ["call_prefix.wav", "7.wav"]


def test_room_value_prefers_digits_then_name():
    assert audio.room_value(type("S", (), {"name": "ห้อง 13"})()) == "13"
    assert audio.room_value(type("S", (), {"name": "ER"})()) == "ER"


def test_get_audio_config_defaults_and_override():
    assert audio.get_audio_config(None)["template"] == audio.DEFAULT_TEMPLATE
    cfg = audio.get_audio_config(type("C", (), {"audio_config": {"volume": 0.5, "template": None}})())
    assert cfg["volume"] == 0.5
    assert cfg["template"] == audio.DEFAULT_TEMPLATE   # null template -> fall back to default


def test_get_audio_config_coerces_bad_volume_repeat():
    # tenant typo in JSONB must not crash the public display -> coerce to numeric defaults
    cfg = audio.get_audio_config(type("C", (), {"audio_config": {"volume": "high", "repeat": "x"}})())
    assert cfg["volume"] == 1.0 and cfg["repeat"] == 1
    cfg2 = audio.get_audio_config(type("C", (), {"audio_config": {"volume": 0}})())
    assert cfg2["volume"] == 0.0   # explicit mute preserved (not coerced to 1)


def demo():
    # runnable check: fallback chain is the load-bearing logic
    assert audio.build_playlist(["{queue}"], {"queue": "42"}, {"4", "2"}) == ["4.wav", "2.wav"]
    assert audio.build_playlist(["{queue}"], {"queue": "42"}, {"42"}) == ["42.wav"]
    print("audio_service demo OK")


if __name__ == "__main__":
    demo()
