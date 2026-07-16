"""SETUP-WIZARD: scripts/seed.py no longer auto-creates an admin with a
random generated password printed to the deploy log. seed_admin() is now
strictly opt-in -- it only creates an admin when the environment supplies
*both* ADMIN_EMAIL and ADMIN_PASSWORD (e.g. CI/automated-test setups that
need a deterministic account without driving the UI). The normal
first-run bootstrap path for humans is the `/api/v1/setup` wizard, covered
by tests/test_setup.py.
"""

from __future__ import annotations

from scripts.seed import seed_admin
from sqlalchemy import select

from app.config import reset_settings_cache
from app.models.user import User


async def test_seed_admin_skips_when_neither_env_var_set(db_session, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    reset_settings_cache()
    try:
        created = await seed_admin(db_session)
        assert created is False

        result = await db_session.execute(select(User))
        assert result.scalars().all() == []
    finally:
        reset_settings_cache()


async def test_seed_admin_skips_when_only_email_set(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "only-email@example.com")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    reset_settings_cache()
    try:
        created = await seed_admin(db_session)
        assert created is False

        result = await db_session.execute(
            select(User).where(User.email == "only-email@example.com")
        )
        assert result.scalar_one_or_none() is None
    finally:
        reset_settings_cache()


async def test_seed_admin_skips_when_only_password_set(db_session, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.setenv("ADMIN_PASSWORD", "Sup3rSecretAdmin!")
    reset_settings_cache()
    try:
        created = await seed_admin(db_session)
        assert created is False

        result = await db_session.execute(select(User))
        assert result.scalars().all() == []
    finally:
        reset_settings_cache()


async def test_seed_admin_creates_when_both_env_vars_set(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "Custom-Admin@Example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sup3rSecretAdmin!")
    reset_settings_cache()
    try:
        created = await seed_admin(db_session)
        assert created is True

        # Email is normalized (stripped + lowercased), same as before.
        result = await db_session.execute(
            select(User).where(User.email == "custom-admin@example.com")
        )
        user = result.scalar_one()
        assert user.email == "custom-admin@example.com"
        assert user.role.value == "admin"
    finally:
        reset_settings_cache()


async def test_seed_admin_is_idempotent(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "idempotent-admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sup3rSecretAdmin!")
    reset_settings_cache()
    try:
        first_created = await seed_admin(db_session)
        assert first_created is True

        second_created = await seed_admin(db_session)
        assert second_created is False

        result = await db_session.execute(select(User))
        assert len(result.scalars().all()) == 1
    finally:
        reset_settings_cache()
