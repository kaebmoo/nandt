"""
Migration: Telegram control-plane account pool (Phase 4.6b / §4.11).

Creates public-schema metadata tables for SaaS-managed Telegram bot accounts.
Bot tokens are intentionally not stored here; tenant tokens remain encrypted in
tenant.messaging_config.telegram_bot_token_enc.

Usage:
    python migrations/add_telegram_pool_structures.py
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL ไม่ถูกตั้งใน .env")
    sys.exit(1)


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS public.saas_telegram_accounts (
        id           SERIAL PRIMARY KEY,
        label        VARCHAR(100) NOT NULL UNIQUE,
        bot_capacity SMALLINT NOT NULL DEFAULT 20,
        status       VARCHAR(10) NOT NULL DEFAULT 'active',
        contact_note TEXT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK (bot_capacity > 0),
        CHECK (status IN ('active', 'full', 'disabled'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.saas_telegram_bots (
        id              SERIAL PRIMARY KEY,
        saas_account_id INTEGER NOT NULL REFERENCES public.saas_telegram_accounts(id),
        tenant_schema   VARCHAR(63) REFERENCES public.hospitals(schema_name),
        bot_username    VARCHAR(100) NOT NULL UNIQUE,
        status          VARCHAR(10) NOT NULL DEFAULT 'allocated',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK (status IN ('allocated', 'spare', 'revoked'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_saas_tg_bots_account ON public.saas_telegram_bots (saas_account_id)",
    "CREATE INDEX IF NOT EXISTS idx_saas_tg_bots_tenant ON public.saas_telegram_bots (tenant_schema)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_saas_tg_bots_allocated_tenant
        ON public.saas_telegram_bots (tenant_schema)
        WHERE tenant_schema IS NOT NULL AND status = 'allocated'
    """,
]


def main():
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for statement in DDL_STATEMENTS:
            conn.execute(text(statement))
    print("✅ Telegram pool control-plane structures ready")


if __name__ == "__main__":
    main()
