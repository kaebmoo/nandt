#!/usr/bin/env python3
"""Telegram long-polling consumer — LOCAL DEV ONLY (no public HTTPS needed).

Two delivery modes for the same bot:
  • webhook  (production)  — provision_telegram_bot() calls setWebhook; Telegram
                             POSTs updates to https://<tenant>/webhooks/telegram/<key>.
  • polling  (this script) — getUpdates long-poll over plain http, for testing on
                             localhost where you have no public HTTPS endpoint.

getUpdates and webhooks are mutually exclusive, so this script first deletes the
webhook for each bot, then long-polls and feeds every update through the SAME
handler the webhook uses (webhook_routes.handle_telegram_update). Switch back to
webhook for deploy by re-saving the Telegram settings (re-provision → setWebhook).

Run from the repo root (loads .env, needs MESSAGING_ENCRYPTION_KEYS for the token):

    PYTHONPATH=. python telegram_poller.py

What works over plain http: the bot RECEIVING commands and replying — send
`/start sp_<id>` to your bot and it replies with the check-in button. What still
needs HTTPS (use a tunnel like cloudflared): TAPPING a Telegram web_app button to
open the Mini App, and LIFF / identity linking.

ponytail: dev tool. Sequential long-poll, in-memory offset per run, no DB column,
no new dependency. Sequential across tenants is fine for 1–2 dev bots; run one
poller per bot (or thread them) only if you ever test many tenants at once.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()  # must precede shared_db import (engine reads DATABASE_URL at import)

import os
import time

import requests
from sqlalchemy import text

from shared_db import crypto
from shared_db.database import SessionLocal, bind_tenant
from shared_db.models import Hospital, HospitalStatus
from flask_app.app.webhook_routes import handle_telegram_update, _get_config

POLL_TIMEOUT = int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "20"))           # long-poll seconds
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5001/")
_API = "https://api.telegram.org/bot{token}/{method}"


def _reset_close(db) -> None:
    """Return the connection to the pool on a clean public search_path."""
    bind_tenant(db, None)
    try:
        db.execute(text("SET search_path TO public"))
        db.commit()
    except Exception:
        db.rollback()
    db.close()


def _telegram_tenants() -> list[tuple[str, str, str]]:
    """Return (schema, subdomain, decrypted_token) for tenants with Telegram active."""
    out: list[tuple[str, str, str]] = []
    db = SessionLocal()
    try:
        bind_tenant(db, None)
        db.execute(text("SET search_path TO public"))
        rows = [(h.schema_name, h.subdomain)
                for h in db.query(Hospital)
                .filter(Hospital.status == HospitalStatus.ACTIVE).all()]
    finally:
        _reset_close(db)

    for schema, subdomain in rows:
        tdb = SessionLocal()
        try:
            bind_tenant(tdb, schema)
            tdb.execute(text(f'SET search_path TO "{schema}", public'))
            cfg = _get_config(tdb)
            token_enc = getattr(cfg, "telegram_bot_token_enc", None)
            if token_enc and getattr(cfg, "telegram_status", None) == "active":
                out.append((schema, subdomain, crypto.decrypt(token_enc)))
        finally:
            _reset_close(tdb)
    return out


def _delete_webhook(token: str) -> None:
    # drop_pending_updates=False so messages sent while you were on webhook still arrive
    requests.post(_API.format(token=token, method="deleteWebhook"),
                  json={"drop_pending_updates": False}, timeout=15)


def _get_updates(token: str, offset: int | None) -> list[dict]:
    resp = requests.post(
        _API.format(token=token, method="getUpdates"),
        json={"offset": offset, "timeout": POLL_TIMEOUT},
        timeout=POLL_TIMEOUT + 10,
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or "getUpdates failed")
    return data.get("result", [])


def _process(schema: str, subdomain: str, update: dict) -> None:
    db = SessionLocal()
    try:
        bind_tenant(db, schema)
        db.execute(text(f'SET search_path TO "{schema}", public'))
        handle_telegram_update(db, update, config=_get_config(db),
                               public_base_url=PUBLIC_BASE_URL, subdomain=subdomain)
    except Exception as exc:  # never let one bad update kill the loop
        print(f"[telegram-poll] {schema} update {update.get('update_id')} FAILED: {exc}")
        db.rollback()
    finally:
        _reset_close(db)


def main() -> None:
    tenants = _telegram_tenants()
    if not tenants:
        print("No tenant has Telegram active (telegram_status='active' + a saved token).\n"
              "Provision a bot in /settings/messaging first, then re-run.")
        return

    print("⚠️  Switching these bots to POLLING — this deletes their webhook. "
          "Re-provision (re-save Telegram settings) to restore webhook for deploy.")
    for schema, subdomain, token in tenants:
        _delete_webhook(token)
        print(f"[telegram-poll] polling {schema} (subdomain={subdomain})")
    print(f"[telegram-poll] long-poll timeout={POLL_TIMEOUT}s, base={PUBLIC_BASE_URL}. Ctrl+C to stop.")

    offsets: dict[str, int | None] = {schema: None for schema, _, _ in tenants}
    while True:
        for schema, subdomain, token in tenants:
            try:
                updates = _get_updates(token, offsets[schema])
            except Exception as exc:
                print(f"[telegram-poll] {schema} getUpdates error: {exc}")
                time.sleep(3)
                continue
            for upd in updates:
                _process(schema, subdomain, upd)
                offsets[schema] = upd["update_id"] + 1


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[telegram-poll] stopped.")
