#!/usr/bin/env python3
"""LINE Rich Menu setup (Phase 4.4) — one-time per tenant, needs a real LINE channel.

There is no localhost path for this: the rich menu lives on LINE's servers and its
buttons open your LIFF app (HTTPS). Run it once after the tenant's LINE channel is
configured in /settings/messaging (line_status='active', channel token + line_liff_id
saved):

    PYTHONPATH=. python line_rich_menu.py --subdomain humnoi --image rich_menu.png

The image is YOUR design. LINE spec: width 2500px, height 843 (compact, --size compact)
or 1686 (full, --size full), PNG/JPEG, < 1 MB — the declared height must match the
image. This script deletes any existing rich menus (so re-running doesn't pile them
up), creates a 3-button menu (จองนัด / เช็คอิน / ดูคิว) that all open your LIFF app,
uploads the image, and sets it as the default for every user.

ponytail: setup tool, not in the test suite (needs live LINE creds). Edit _LABELS /
_menu_body() to change the layout. No new dependency.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()  # before shared_db import (engine reads DATABASE_URL at import)

import argparse
import os
import sys

import requests
from sqlalchemy import text

from shared_db import crypto, models
from shared_db.database import SessionLocal, bind_tenant

_API = "https://api.line.me/v2/bot"
_DATA_API = "https://api-data.line.me/v2/bot"
_LABELS = ["จองนัด", "เช็คอิน", "ดูคิว"]
_SIZES = {"compact": 843, "full": 1686}


def _fail(message: str) -> None:
    print(f"❌ {message}")
    sys.exit(1)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _load_tenant(subdomain: str) -> tuple[str, str, str]:
    """Return (schema, decrypted LINE token, liff_id) for the tenant, or exit."""
    db = SessionLocal()
    try:
        bind_tenant(db, None)
        db.execute(text("SET search_path TO public"))
        row = db.execute(
            text("SELECT schema_name FROM public.hospitals "
                 "WHERE subdomain = :s OR schema_name = :s LIMIT 1"),
            {"s": subdomain},
        ).first()
        if not row:
            _fail(f"ไม่พบ tenant: {subdomain}")
        schema = row[0]
        bind_tenant(db, schema)
        db.execute(text(f'SET search_path TO "{schema}", public'))
        cfg = db.query(models.MessagingConfig).order_by(models.MessagingConfig.id.asc()).first()
        token_enc = getattr(cfg, "line_channel_token_enc", None)
        liff_id = getattr(cfg, "line_liff_id", None)
        if getattr(cfg, "line_status", None) != "active" or not token_enc:
            _fail("tenant นี้ยังไม่ได้ตั้งค่า LINE ให้ active + ใส่ channel token (ที่ /settings/messaging)")
        if not liff_id:
            _fail("ยังไม่ได้ตั้ง line_liff_id — ปุ่มเมนูต้องเปิด LIFF (ตั้งที่ /settings/messaging)")
        return schema, crypto.decrypt(token_enc), liff_id
    finally:
        bind_tenant(db, None)
        try:
            db.execute(text("SET search_path TO public"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def _menu_body(liff_url: str, height: int) -> dict:
    third = 2500 // 3
    areas = []
    for i, label in enumerate(_LABELS):
        x = i * third
        width = (2500 - x) if i == len(_LABELS) - 1 else third  # last column eats the rounding
        areas.append({
            "bounds": {"x": x, "y": 0, "width": width, "height": height},
            "action": {"type": "uri", "label": label, "uri": liff_url},
        })
    return {
        "size": {"width": 2500, "height": height},
        "selected": True,
        "name": "NudDee menu",
        "chatBarText": "เมนู NudDee",
        "areas": areas,
    }


def _delete_existing(token: str) -> None:
    resp = requests.get(f"{_API}/richmenu/list", headers=_auth(token), timeout=15)
    if resp.status_code >= 400:
        _fail(f"อ่านรายการ rich menu เดิมไม่ได้: {resp.status_code} {resp.text}")
    for menu in resp.json().get("richmenus", []):
        rid = menu.get("richMenuId")
        requests.delete(f"{_API}/richmenu/{rid}", headers=_auth(token), timeout=15)
        print(f"  - ลบ rich menu เดิม {rid}")


def _create(token: str, body: dict) -> str:
    resp = requests.post(f"{_API}/richmenu",
                         headers={**_auth(token), "Content-Type": "application/json"},
                         json=body, timeout=15)
    if resp.status_code >= 400:
        _fail(f"createRichMenu ล้มเหลว: {resp.status_code} {resp.text}")
    return resp.json()["richMenuId"]


def _upload_image(token: str, rid: str, image_path: str) -> None:
    ctype = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    with open(image_path, "rb") as fh:
        data = fh.read()
    resp = requests.post(f"{_DATA_API}/richmenu/{rid}/content",
                         headers={**_auth(token), "Content-Type": ctype},
                         data=data, timeout=30)
    if resp.status_code >= 400:
        _fail(f"อัปโหลดรูปล้มเหลว: {resp.status_code} {resp.text}\n"
              f"   LINE ต้องการ 2500×(843|1686) px, PNG/JPEG, <1MB และต้องตรงกับ --size")


def _set_default(token: str, rid: str) -> None:
    resp = requests.post(f"{_API}/user/all/richmenu/{rid}", headers=_auth(token), timeout=15)
    if resp.status_code >= 400:
        _fail(f"setDefaultRichMenu ล้มเหลว: {resp.status_code} {resp.text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ตั้งค่า LINE Rich Menu ให้ tenant")
    parser.add_argument("--subdomain", required=True, help="subdomain หรือ schema ของ tenant")
    parser.add_argument("--image", required=True, help="ไฟล์รูปเมนู (2500×843 หรือ 2500×1686)")
    parser.add_argument("--size", choices=_SIZES, default="compact",
                        help="compact=843px (default) / full=1686px — ต้องตรงกับความสูงรูป")
    args = parser.parse_args()

    if not os.path.isfile(args.image):
        _fail(f"ไม่พบไฟล์รูป: {args.image}")

    schema, token, liff_id = _load_tenant(args.subdomain)
    liff_url = f"https://liff.line.me/{liff_id}"
    print(f"tenant={schema}  liff={liff_url}  size={args.size}")

    _delete_existing(token)
    rid = _create(token, _menu_body(liff_url, _SIZES[args.size]))
    print(f"  + สร้าง rich menu {rid}")
    _upload_image(token, rid, args.image)
    print("  + อัปโหลดรูปแล้ว")
    _set_default(token, rid)
    print(f"✅ ตั้ง rich menu เป็น default ให้ทุกคนแล้ว ({rid})")


if __name__ == "__main__":
    main()
