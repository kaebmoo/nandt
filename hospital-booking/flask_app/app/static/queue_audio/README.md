# Queue-call audio clips (Patch 21 §14)

The display screen announces a called queue by **playing a list of WAV clips in order**
(concatenative). The server builds the playlist (`services/audio_service.py`); the browser
just plays the files.

## Layout
```
queue_audio/
  _default/            # shipped Thai set — fallback for every tenant
  <schema_name>/       # per-tenant overrides (e.g. tenant_humnoi/) — optional
```
A clip is looked up in the tenant folder first, then `_default/`.

## Required default clips (basename → spoken text)
- `0.wav` … `9.wav` — the digits ศูนย์…เก้า
- `call_prefix.wav` — "เชิญหมายเลข"
- `room_prefix.wav` — "ที่ห้อง"

> ⚠️ The `_default/*.wav` shipped here are **placeholder tones**, not speech — replace them
> with real Thai recordings (8 kHz/16 kHz mono WAV is fine). Code does not change.

## Template
The spoken order is a token list in `messaging_config.audio_config.template`, default:
```json
["call_prefix", "{queue}", "room_prefix", "{room}"]
```
- literal token → plays `<token>.wav`
- `{queue}` / `{room}` → plays `<full>.wav` if recorded (e.g. `355.wav`), else reads each
  digit (`3.wav 5.wav 5.wav`). Want full-number readout? record `355.wav`. No code change.

## Per-tenant audio_config (JSONB on messaging_config)
```json
{"enabled": true, "template": [...], "volume": 1.0, "repeat": 1,
 "rooms": {"<service_point_id>": {"enabled": false}}}
```
Letters/series (e.g. "L") are intentionally not spoken — record a clip + add to the
template if a tenant wants them.
