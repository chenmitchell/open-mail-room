from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Make `app` / `scripts` importable no matter how pytest was invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _configure_env(monkeypatch):
    """Fresh SECRET_KEY/ENCRYPTION_KEY/DATABASE_URL for every test.

    Keys are generated per-test (never hardcoded) per project policy: "測試
    用的 key 在 conftest 內產生".
    """
    monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(32))
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("LOGIN_LOCKOUT_MINUTES", "15")
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    # SETUP-WIZARD: scripts/seed.py's admin auto-creation is opt-in, keyed
    # off these two being set (see app/config.py Settings.admin_email/
    # admin_password). Cleared here so no stray environment leaks a
    # would-be admin into a test that doesn't ask for one; individual
    # seed_admin tests (tests/test_seed_admin.py) set them explicitly.
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    from app.config import reset_settings_cache

    reset_settings_cache()

    from app.security.rate_limit import (
        reset_login_rate_limiter,
        reset_pickup_code_rate_limiters,
        reset_setup_rate_limiter,
        reset_webhook_ip_rate_limiters,
    )

    reset_login_rate_limiter()
    reset_pickup_code_rate_limiters()
    reset_webhook_ip_rate_limiters()
    reset_setup_rate_limiter()

    yield

    reset_settings_cache()
    reset_login_rate_limiter()
    reset_pickup_code_rate_limiters()
    reset_webhook_ip_rate_limiters()
    reset_setup_rate_limiter()


@pytest_asyncio.fixture
async def db_engine(_configure_env):
    """A clean in-memory SQLite schema for a single test."""
    from app.db import get_engine, reset_db_state

    await reset_db_state()
    engine = get_engine()

    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await reset_db_state()


@pytest_asyncio.fixture
async def app(db_engine):
    from app.main import create_app

    return create_app()


def _cookie_value(header_value: str | None, name: str) -> str | None:
    if not header_value:
        return None
    for part in header_value.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return None


async def _attach_csrf_header(request) -> None:
    """Test-client stand-in for what a real browser + frontend/src/api/
    client.ts does: echo the `csrf_token` cookie back as the `X-CSRF-Token`
    header on every non-safe-method request (M1-R1 blocking #4 moved CSRF
    enforcement from "only /logout" to "every write endpoint"; rather than
    hand-editing every one of the ~80 existing request call sites across the
    test suite to add this header, the test client attaches it the same way
    a real browser would -- automatically, from the cookie jar).

    Mirrors client.ts's SAFE_METHODS carve-out and never overwrites a header
    a test set explicitly (e.g. a deliberately wrong/missing-CSRF test).
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if "x-csrf-token" in request.headers:
        return
    token = _cookie_value(request.headers.get("cookie"), "csrf_token")
    if token:
        request.headers["x-csrf-token"] = token


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        event_hooks={"request": [_attach_csrf_header]},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session(db_engine):
    from app.db import get_sessionmaker

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def admin_user(db_session):
    """SETUP-WIZARD: many existing tests assume an admin account already
    exists (the old default was scripts/seed.py auto-creating one on every
    boot). Admin creation is no longer automatic -- it's either the
    first-run `/api/v1/setup` wizard or an opt-in ADMIN_EMAIL/ADMIN_PASSWORD
    env pair for automation (see app/api/v1/setup.py, scripts/seed.py).
    Tests that just need *some* logged-in admin (rather than exercising the
    setup flow itself) can depend on this fixture to create one directly
    against the DB, bypassing both of those paths -- same shape as
    tests/_helpers.py's `create_user`/`login_as`, just as a reusable
    fixture for tests that don't already import that helper.
    """
    from app.models.enums import UserRole
    from app.models.user import User
    from app.security.passwords import hash_password

    user = User(
        email="admin@example.com",
        password_hash=hash_password("Sup3rSecret!"),
        display_name="Administrator",
        role=UserRole.admin,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
