"""Async SQLAlchemy engine/session setup.

Driver is picked automatically from DATABASE_URL:
- sqlite://...            -> sqlite+aiosqlite://...
- postgres(ql)://...      -> postgresql+asyncpg://...
Explicit +driver URLs are passed through untouched.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import get_settings


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        return "sqlite+aiosqlite://" + url[len("sqlite://") :]
    return url


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = normalize_database_url(get_settings().database_url)
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                # In-memory sqlite is per-connection; share one connection
                # across the whole engine so all sessions see the same DB.
                kwargs["poolclass"] = StaticPool
        _engine = create_async_engine(url, **kwargs)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        yield session


async def check_db_ready() -> bool:
    """Readiness check: the DB must be reachable *and* migrated.

    A bare `SELECT 1` succeeds against a completely empty database (no
    tables at all), which made /readyz report "ok" on a freshly created but
    never-migrated deployment (M0-R1 blocking #7). Querying the `users`
    table instead fails until `alembic upgrade head` has actually run.
    """
    from sqlalchemy import text

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM users LIMIT 1"))
        return True
    except Exception:
        return False


async def reset_db_state() -> None:
    """Dispose engine/sessionmaker so a fresh Settings.database_url is honored.

    Used by tests when they need a clean, isolated in-memory database.
    """
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
