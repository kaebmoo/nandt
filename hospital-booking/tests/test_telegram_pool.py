import pytest
from sqlalchemy import text

from flask_app.app.services import telegram_pool
from shared_db import models


@pytest.fixture()
def telegram_pool_public(engine, db):
    with engine.begin() as conn:
        models.PublicBase.metadata.create_all(bind=conn)

    def cleanup():
        (db.query(models.SaasTelegramBot)
         .filter(models.SaasTelegramBot.tenant_schema.like("pool_test_%"))
         .delete(synchronize_session=False))
        (db.query(models.SaasTelegramBot)
         .filter(models.SaasTelegramBot.bot_username.like("pool_test_%"))
         .delete(synchronize_session=False))
        (db.query(models.SaasTelegramAccount)
         .filter(models.SaasTelegramAccount.label.like("pool_test_%"))
         .delete(synchronize_session=False))
        (db.query(models.Hospital)
         .filter(models.Hospital.schema_name.like("pool_test_%"))
         .delete(synchronize_session=False))
        schemas = (db.execute(text("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE 'pool_test_%'
        """)).scalars().all())
        for schema in schemas:
            db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        db.commit()

    cleanup()
    yield
    cleanup()


def _hospital(db, suffix):
    schema_name = f"pool_test_{suffix}"
    db.execute(text("""
        INSERT INTO public.hospitals (name, subdomain, schema_name, status)
        VALUES (:name, :subdomain, :schema_name, 'active')
        ON CONFLICT (schema_name) DO UPDATE
        SET name = EXCLUDED.name,
            subdomain = EXCLUDED.subdomain,
            status = EXCLUDED.status
    """), {
        "name": f"Pool Test {suffix}",
        "subdomain": f"pool-test-{suffix}",
        "schema_name": schema_name,
    })
    db.commit()
    return schema_name


def test_allocate_account_skips_accounts_at_capacity(db, telegram_pool_public):
    h1 = _hospital(db, "one")
    acc1 = models.SaasTelegramAccount(label="pool_test_1", bot_capacity=1, status="active")
    acc2 = models.SaasTelegramAccount(label="pool_test_2", bot_capacity=2, status="active")
    db.add_all([acc1, acc2])
    db.commit()
    db.add(models.SaasTelegramBot(
        saas_account_id=acc1.id,
        tenant_schema=h1,
        bot_username="pool_test_one_bot",
        status="allocated",
    ))
    db.commit()

    selected = telegram_pool.allocate_account(db)

    assert selected.id == acc2.id


def test_register_bot_rechecks_capacity_and_marks_full(db, telegram_pool_public):
    hospital = _hospital(db, "two")
    acc = models.SaasTelegramAccount(label="pool_test_single", bot_capacity=1, status="active")
    db.add(acc)
    db.commit()

    bot = telegram_pool.register_bot(
        db,
        saas_account_id=acc.id,
        tenant_schema=hospital,
        bot_username="@pool_test_two_bot",
    )

    assert bot.tenant_schema == "pool_test_two"
    assert bot.bot_username == "pool_test_two_bot"
    assert bot.status == "allocated"
    db.refresh(acc)
    assert acc.status == "full"
    assert not hasattr(bot, "token")


def test_register_bot_is_idempotent_for_same_allocation(db, telegram_pool_public):
    hospital = _hospital(db, "three")
    acc = models.SaasTelegramAccount(label="pool_test_idempotent", bot_capacity=2, status="active")
    db.add(acc)
    db.commit()

    first = telegram_pool.register_bot(
        db,
        saas_account_id=acc.id,
        tenant_schema=hospital,
        bot_username="pool_test_three_bot",
    )
    second = telegram_pool.register_bot(
        db,
        saas_account_id=acc.id,
        tenant_schema=hospital,
        bot_username="pool_test_three_bot",
    )

    assert second.id == first.id
    assert (db.query(models.SaasTelegramBot)
            .filter_by(tenant_schema=hospital, status="allocated")
            .count()) == 1


def test_register_bot_idempotent_after_account_marked_full(db, telegram_pool_public):
    # capacity=1: the first allocation fills the account and marks it "full".
    # Retrying the SAME allocation must still return it, not raise PoolExhausted.
    hospital = _hospital(db, "six")
    acc = models.SaasTelegramAccount(label="pool_test_full_retry", bot_capacity=1, status="active")
    db.add(acc)
    db.commit()

    first = telegram_pool.register_bot(
        db, saas_account_id=acc.id, tenant_schema=hospital,
        bot_username="pool_test_six_bot",
    )
    db.refresh(acc)
    assert acc.status == "full"

    second = telegram_pool.register_bot(
        db, saas_account_id=acc.id, tenant_schema=hospital,
        bot_username="pool_test_six_bot",
    )
    assert second.id == first.id


def test_register_bot_rejects_over_capacity_account(db, telegram_pool_public):
    h1 = _hospital(db, "four")
    h2 = _hospital(db, "five")
    acc = models.SaasTelegramAccount(label="pool_test_full", bot_capacity=1, status="active")
    db.add(acc)
    db.commit()
    telegram_pool.register_bot(
        db,
        saas_account_id=acc.id,
        tenant_schema=h1,
        bot_username="pool_test_four_bot",
    )

    with pytest.raises(telegram_pool.PoolExhausted):
        telegram_pool.register_bot(
            db,
            saas_account_id=acc.id,
            tenant_schema=h2,
            bot_username="pool_test_five_bot",
        )
