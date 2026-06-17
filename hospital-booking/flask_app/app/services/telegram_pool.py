"""Control-plane helpers for SaaS-managed Telegram account pool (§4.11)."""

from __future__ import annotations

from sqlalchemy import func

from shared_db import models


class PoolExhausted(RuntimeError):
    """No active SaaS Telegram account has remaining bot capacity."""


class TelegramPoolError(RuntimeError):
    """Telegram pool allocation or registration failed."""


def _allocated_count(db, account_id: int) -> int:
    return (db.query(func.count(models.SaasTelegramBot.id))
            .filter(models.SaasTelegramBot.saas_account_id == account_id,
                    models.SaasTelegramBot.status == "allocated")
            .scalar() or 0)


def allocate_account(db) -> models.SaasTelegramAccount:
    """Return an active account with remaining capacity.

    This is an advisory selection step. `register_bot()` re-checks capacity under
    row lock before inserting the allocation, so concurrent onboarding cannot
    overfill an account.
    """
    accounts = (db.query(models.SaasTelegramAccount)
                .filter(models.SaasTelegramAccount.status == "active")
                .order_by(models.SaasTelegramAccount.id.asc())
                .all())
    for account in accounts:
        if _allocated_count(db, account.id) < int(account.bot_capacity):
            return account
    raise PoolExhausted("telegram account pool exhausted")


def register_bot(db, *, saas_account_id: int, tenant_schema: str,
                 bot_username: str) -> models.SaasTelegramBot:
    """Register a created bot to a tenant after BotFather setup.

    The account row is locked and capacity is re-counted before insert. Tokens
    are not accepted here and must stay in tenant.messaging_config encrypted.
    """
    tenant_schema = (tenant_schema or "").strip()
    bot_username = (bot_username or "").strip().lstrip("@")
    if not tenant_schema:
        raise TelegramPoolError("tenant_schema is required")
    if not bot_username:
        raise TelegramPoolError("bot_username is required")

    account = (db.query(models.SaasTelegramAccount)
               .filter(models.SaasTelegramAccount.id == saas_account_id)
               .with_for_update()
               .one_or_none())
    if account is None:
        raise TelegramPoolError("telegram account not found")

    # Idempotency check BEFORE the status gate: a retry of an allocation that
    # already filled this account (status now "full") must still return that
    # allocation rather than fail with PoolExhausted.
    existing = (db.query(models.SaasTelegramBot)
                .filter(models.SaasTelegramBot.tenant_schema == tenant_schema,
                        models.SaasTelegramBot.status == "allocated")
                .one_or_none())
    if existing is not None:
        if existing.saas_account_id == account.id and existing.bot_username == bot_username:
            return existing
        raise TelegramPoolError("tenant already has an allocated Telegram bot")

    if account.status != "active":
        raise PoolExhausted("telegram account is not active")

    allocated = _allocated_count(db, account.id)
    if allocated >= int(account.bot_capacity):
        account.status = "full"
        db.commit()
        raise PoolExhausted("telegram account capacity reached")

    bot = models.SaasTelegramBot(
        saas_account_id=account.id,
        tenant_schema=tenant_schema,
        bot_username=bot_username,
        status="allocated",
    )
    db.add(bot)
    if allocated + 1 >= int(account.bot_capacity):
        account.status = "full"
    db.commit()
    db.refresh(bot)
    return bot
