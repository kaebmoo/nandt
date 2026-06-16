import importlib

from sqlalchemy import text

from shared_db import models

MIGRATION_SCHEMA = "test_queue_migration_drift"


TABLE_MODELS = [
    models.ServiceSession,
    models.QueueEntry,
    models.QueueEvent,
    models.ChannelLink,
    models.MessagingConfig,
    models.NotificationLog,
    models.QueuePolicy,
    models.GracePolicy,
]


def _db_columns(conn, schema_name, table_name):
    return set(conn.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
        """),
        {"schema_name": schema_name, "table_name": table_name},
    ).scalars().all())


def _model_columns(model):
    return {column.name for column in model.__table__.columns}


def test_queue_messaging_migration_columns_match_models(engine):
    migration = importlib.import_module("migrations.add_queue_messaging_structures")

    try:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{MIGRATION_SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{MIGRATION_SCHEMA}"'))
            conn.execute(text(f'SET search_path TO "{MIGRATION_SCHEMA}", public'))
            conn.execute(text("""
                CREATE TABLE appointments (
                    id SERIAL PRIMARY KEY,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP
                )
            """))

            migration.migrate_schema(conn, MIGRATION_SCHEMA)

            drift = {}
            for model in TABLE_MODELS:
                table_name = model.__tablename__
                expected = _model_columns(model)
                actual = _db_columns(conn, MIGRATION_SCHEMA, table_name)
                missing = sorted(expected - actual)
                extra = sorted(actual - expected)
                if missing or extra:
                    drift[table_name] = {"missing": missing, "extra": extra}

            assert drift == {}
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{MIGRATION_SCHEMA}" CASCADE'))
