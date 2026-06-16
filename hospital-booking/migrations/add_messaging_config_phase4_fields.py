"""
Migration: Phase 4.0 messaging_config upgrade fields.

Adds the final §4.7 channel status/error/provisioning fields to existing
tenant messaging_config tables. New tenants already get these columns from
add_queue_messaging_structures.py; this script upgrades older tables.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL is not set")
    sys.exit(1)


DDL_STATEMENTS = [
    """
    ALTER TABLE messaging_config
        ADD COLUMN IF NOT EXISTS line_login_channel_id        VARCHAR(100),
        ADD COLUMN IF NOT EXISTS line_status                  VARCHAR(20) NOT NULL DEFAULT 'not_configured',
        ADD COLUMN IF NOT EXISTS line_last_error              TEXT,
        ADD COLUMN IF NOT EXISTS telegram_bot_ownership       VARCHAR(10) NOT NULL DEFAULT 'saas',
        ADD COLUMN IF NOT EXISTS telegram_webhook_secret_enc  TEXT,
        ADD COLUMN IF NOT EXISTS telegram_mini_app_short_name VARCHAR(100),
        ADD COLUMN IF NOT EXISTS telegram_status              VARCHAR(20) NOT NULL DEFAULT 'not_configured',
        ADD COLUMN IF NOT EXISTS telegram_last_error          TEXT,
        ADD COLUMN IF NOT EXISTS pwa_status                   VARCHAR(20) NOT NULL DEFAULT 'disabled',
        ADD COLUMN IF NOT EXISTS pwa_vapid_public_key         TEXT,
        ADD COLUMN IF NOT EXISTS pwa_vapid_private_key_enc    TEXT
    """,
    """
    DO $$
    BEGIN
        ALTER TABLE messaging_config
            ADD CONSTRAINT messaging_config_telegram_bot_ownership_check
            CHECK (telegram_bot_ownership IN ('saas', 'tenant'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    DO $$
    BEGIN
        ALTER TABLE messaging_config
            ADD CONSTRAINT messaging_config_line_status_check
            CHECK (line_status IN ('not_configured', 'active', 'error', 'disabled'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    DO $$
    BEGIN
        ALTER TABLE messaging_config
            ADD CONSTRAINT messaging_config_telegram_status_check
            CHECK (telegram_status IN ('not_configured', 'active', 'error', 'disabled'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    DO $$
    BEGIN
        ALTER TABLE messaging_config
            ADD CONSTRAINT messaging_config_pwa_status_check
            CHECK (pwa_status IN ('disabled', 'active', 'error'));
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    """,
]


def resolve_schemas(engine, argv) -> list[str]:
    if "--all" in argv:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT schema_name FROM public.hospitals ORDER BY id")
            ).fetchall()
        return [row[0] for row in rows]

    explicit = [arg for arg in argv if not arg.startswith("--")]
    return explicit or ["tenant_humnoi"]


def migrate_schema(conn, schema_name: str) -> None:
    print(f"migrating {schema_name} ...")
    conn.execute(text(f'SET search_path TO "{schema_name}", public'))
    exists = conn.execute(text("SELECT to_regclass('messaging_config')")).scalar()
    if exists is None:
        print(f"  skipped {schema_name}: messaging_config does not exist")
        return
    for stmt in DDL_STATEMENTS:
        conn.execute(text(stmt))
    print(f"  done {schema_name}")


def main() -> bool:
    engine = create_engine(DATABASE_URL)
    schemas = resolve_schemas(engine, sys.argv[1:])
    with engine.begin() as conn:
        for schema_name in schemas:
            migrate_schema(conn, schema_name)
        conn.execute(text("SET search_path TO public"))
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
