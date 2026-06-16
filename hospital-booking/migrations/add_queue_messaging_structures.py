"""
Migration: Queue + Check-in + Messaging foundation (Phase 0)

สร้างตารางตามแผน NudDee_Queue_and_Messaging_Implementation_Plan.md ส่วนที่ 4.1–4.10
+ ALTER appointments (4.3) + seed default rows (service_point / queue_policy / grace_policy / sample session)

ตารางที่สร้าง (ใน tenant schema):
    service_points, sessions, queue_entries, queue_events,
    channel_links, messaging_config, notification_log, queue_policy, grace_policy

วิธีรัน (ปลอดภัย — default รันแค่ tenant_humnoi):
    python migrations/add_queue_messaging_structures.py                 # tenant_humnoi เท่านั้น
    python migrations/add_queue_messaging_structures.py tenant_ccui     # ระบุ schema เอง (รับได้หลายตัว)
    python migrations/add_queue_messaging_structures.py --all           # ทุก tenant จาก public.hospitals

ทุกอย่าง idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS / seed มี guard)
ไม่แตะ public schema (มีแค่ hospitals, users)
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


# --- DDL: ลำดับสำคัญ (FK ต้องมีตารางปลายทางก่อน) ---
# service_points -> sessions -> ALTER appointments -> queue_entries -> queue_events
# -> channel_links -> messaging_config -> notification_log -> queue_policy -> grace_policy
DDL_STATEMENTS = [
    # 4.1 service_points
    """
    CREATE TABLE IF NOT EXISTS service_points (
        id               SERIAL PRIMARY KEY,
        name             VARCHAR(200) NOT NULL,
        sp_type          VARCHAR(20) NOT NULL DEFAULT 'room',
        parallel_servers SMALLINT NOT NULL DEFAULT 1,
        is_active        BOOLEAN NOT NULL DEFAULT TRUE,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # 4.2 sessions
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id               SERIAL PRIMARY KEY,
        service_point_id INTEGER NOT NULL REFERENCES service_points(id),
        session_date     DATE NOT NULL,
        name             VARCHAR(100) NOT NULL,
        start_time       TIME NOT NULL,
        end_time         TIME NOT NULL,
        capacity         INTEGER,
        is_active        BOOLEAN NOT NULL DEFAULT TRUE,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (service_point_id, session_date, name)
    )
    """,
    # 4.3 ALTER appointments (additive, nullable/มี default — ของเดิมไม่พัง)
    """
    ALTER TABLE appointments
        ADD COLUMN IF NOT EXISTS slot_type        VARCHAR(10) NOT NULL DEFAULT 'exact',
        ADD COLUMN IF NOT EXISTS session_id       INTEGER REFERENCES sessions(id),
        ADD COLUMN IF NOT EXISTS service_point_id INTEGER REFERENCES service_points(id),
        ADD COLUMN IF NOT EXISTS appointment_type VARCHAR(100),
        ADD COLUMN IF NOT EXISTS patient_category VARCHAR(50)
    """,
    # 4.4 queue_entries
    """
    CREATE TABLE IF NOT EXISTS queue_entries (
        id               SERIAL PRIMARY KEY,
        appointment_id   INTEGER REFERENCES appointments(id),
        service_point_id INTEGER NOT NULL REFERENCES service_points(id),
        session_id       INTEGER REFERENCES sessions(id),
        session_date     DATE NOT NULL,
        patient_ref      VARCHAR(100) NOT NULL,
        entry_class      VARCHAR(20) NOT NULL DEFAULT 'walkin',
        queue_number     INTEGER,
        status           VARCHAR(20) NOT NULL DEFAULT 'checked_in',
        priority_score   NUMERIC(10,3),
        check_in_at      TIMESTAMPTZ,
        called_at        TIMESTAMPTZ,
        service_start_at TIMESTAMPTZ,
        service_end_at   TIMESTAMPTZ,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_queue_entries_active ON queue_entries (service_point_id, session_date, status)",
    "CREATE INDEX IF NOT EXISTS idx_queue_entries_appt ON queue_entries (appointment_id)",
    # 4.5 queue_events (append-only)
    """
    CREATE TABLE IF NOT EXISTS queue_events (
        id             BIGSERIAL PRIMARY KEY,
        queue_entry_id INTEGER NOT NULL REFERENCES queue_entries(id),
        event_type     VARCHAR(40) NOT NULL,
        from_status    VARCHAR(20),
        to_status      VARCHAR(20),
        actor          VARCHAR(20) NOT NULL DEFAULT 'system',
        occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        metadata       JSONB
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_queue_events_entry ON queue_events (queue_entry_id)",
    "CREATE INDEX IF NOT EXISTS idx_queue_events_time ON queue_events (occurred_at)",
    # 4.6 channel_links
    """
    CREATE TABLE IF NOT EXISTS channel_links (
        id          SERIAL PRIMARY KEY,
        patient_ref VARCHAR(100) NOT NULL,
        channel     VARCHAR(20) NOT NULL,
        external_id VARCHAR(255) NOT NULL,
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        raw_profile JSONB,
        linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (channel, external_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_channel_links_patient ON channel_links (patient_ref)",
    # 4.7 messaging_config (*_enc = encrypted at rest — Fernet)
    """
    CREATE TABLE IF NOT EXISTS messaging_config (
        id                               SERIAL PRIMARY KEY,
        line_channel_id                  VARCHAR(100),
        line_channel_secret_enc          TEXT,
        line_channel_token_enc           TEXT,
        line_login_channel_id            VARCHAR(100),
        line_liff_id                     VARCHAR(100),
        line_status                      VARCHAR(20) NOT NULL DEFAULT 'not_configured',
        line_last_error                  TEXT,
        telegram_bot_token_enc           TEXT,
        telegram_bot_username            VARCHAR(100),
        telegram_bot_ownership           VARCHAR(10) NOT NULL DEFAULT 'saas',
        telegram_webhook_secret_enc      TEXT,
        telegram_mini_app_short_name     VARCHAR(100),
        telegram_status                  VARCHAR(20) NOT NULL DEFAULT 'not_configured',
        telegram_last_error              TEXT,
        pwa_status                       VARCHAR(20) NOT NULL DEFAULT 'disabled',
        pwa_vapid_public_key             TEXT,
        pwa_vapid_private_key_enc        TEXT,
        plan_tier                        VARCHAR(20) DEFAULT 'free',
        channel_priority                 JSONB NOT NULL DEFAULT '["telegram","pwa","line_push"]',
        reminder_enabled                 BOOLEAN NOT NULL DEFAULT FALSE,
        updated_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
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
    # 4.8 notification_log
    """
    CREATE TABLE IF NOT EXISTS notification_log (
        id             BIGSERIAL PRIMARY KEY,
        queue_entry_id INTEGER REFERENCES queue_entries(id),
        patient_ref    VARCHAR(100),
        event_type     VARCHAR(40) NOT NULL,
        channel        VARCHAR(20) NOT NULL,
        cost_units     SMALLINT NOT NULL DEFAULT 0,
        status         VARCHAR(20) NOT NULL,
        sent_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        error          TEXT,
        metadata       JSONB
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notif_log_time ON notification_log (sent_at)",
    # 4.9 queue_policy
    """
    CREATE TABLE IF NOT EXISTS queue_policy (
        id                                 SERIAL PRIMARY KEY,
        service_point_id                   INTEGER REFERENCES service_points(id),
        mode                               VARCHAR(10) NOT NULL DEFAULT 'ratio',
        appointment_to_walkin_ratio        SMALLINT NOT NULL DEFAULT 3,
        walkin_max_wait_minutes            INTEGER NOT NULL DEFAULT 45,
        appointment_early_eligible_minutes INTEGER NOT NULL DEFAULT 15,
        call_timeout_min                   INTEGER NOT NULL DEFAULT 5,
        w_class                            NUMERIC(6,3) NOT NULL DEFAULT 100,
        w_wait                             NUMERIC(6,3) NOT NULL DEFAULT 1,
        w_window                           NUMERIC(6,3) NOT NULL DEFAULT 2,
        updated_at                         TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "ALTER TABLE queue_policy ADD COLUMN IF NOT EXISTS call_timeout_min INTEGER NOT NULL DEFAULT 5",
    # 4.10 grace_policy
    """
    CREATE TABLE IF NOT EXISTS grace_policy (
        id                  SERIAL PRIMARY KEY,
        service_point_id    INTEGER REFERENCES service_points(id),
        grace_before_min    INTEGER NOT NULL DEFAULT 30,
        grace_after_min     INTEGER NOT NULL DEFAULT 30,
        late_arrival_policy  VARCHAR(20) NOT NULL DEFAULT 'demote_to_walkin',
        no_show_grace_min   INTEGER NOT NULL DEFAULT 10,
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]

# --- Seed: default rows (idempotent ด้วย guard) ---
SEED_STATEMENTS = [
    # service_point เริ่มต้น 1 จุด
    """
    INSERT INTO service_points (name, sp_type, parallel_servers)
    SELECT 'จุดบริการหลัก', 'counter', 1
    WHERE NOT EXISTS (SELECT 1 FROM service_points)
    """,
    # queue_policy default ของ tenant (service_point_id = NULL)
    """
    INSERT INTO queue_policy (service_point_id, mode)
    SELECT NULL, 'ratio'
    WHERE NOT EXISTS (SELECT 1 FROM queue_policy WHERE service_point_id IS NULL)
    """,
    # grace_policy default ของ tenant (service_point_id = NULL)
    """
    INSERT INTO grace_policy (service_point_id)
    SELECT NULL
    WHERE NOT EXISTS (SELECT 1 FROM grace_policy WHERE service_point_id IS NULL)
    """,
    # sample session สำหรับ service_point แรก วันนี้ (smoke-test row)
    """
    INSERT INTO sessions (service_point_id, session_date, name, start_time, end_time)
    SELECT sp.id, CURRENT_DATE, 'เช้า', TIME '08:30', TIME '12:00'
    FROM service_points sp
    ORDER BY sp.id
    LIMIT 1
    ON CONFLICT (service_point_id, session_date, name) DO NOTHING
    """,
]


def migrate_schema(conn, schema_name: str) -> None:
    """รัน DDL + seed ทั้งหมดใน schema เดียว (1 transaction)"""
    print(f"\n→ migrating schema '{schema_name}' ...")
    conn.execute(text(f'SET search_path TO "{schema_name}", public'))

    for stmt in DDL_STATEMENTS:
        conn.execute(text(stmt))
    for stmt in SEED_STATEMENTS:
        conn.execute(text(stmt))

    conn.execute(text("SET search_path TO public"))
    print(f"  ✅ '{schema_name}' done (9 tables + appointments columns + seeds)")


def resolve_schemas(engine, argv) -> list:
    """ตัดสินใจว่าจะรัน schema ไหนบ้างจาก argv"""
    if "--all" in argv:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT schema_name FROM public.hospitals ORDER BY id")
            ).fetchall()
        return [r[0] for r in rows]

    explicit = [a for a in argv if not a.startswith("--")]
    if explicit:
        return explicit

    # default ปลอดภัย: humnoi เท่านั้น (ตามที่ตกลงไว้ — รัน+verify ก่อน roll ออก)
    return ["tenant_humnoi"]


def main() -> bool:
    engine = create_engine(DATABASE_URL)
    schemas = resolve_schemas(engine, sys.argv[1:])

    if not schemas:
        print("ไม่พบ tenant schema ที่จะ migrate")
        return True

    print(f"จะ migrate {len(schemas)} schema: {', '.join(schemas)}")
    with engine.begin() as conn:  # transaction เดียวครอบทุก schema — fail แล้ว rollback หมด
        for schema_name in schemas:
            migrate_schema(conn, schema_name)
        conn.execute(text("SET search_path TO public"))

    print("\n🎉 Migration completed")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
