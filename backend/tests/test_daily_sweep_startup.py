"""RC-FIX #6 smoke test: main.py wires app.notify.scheduler.run_daily_reminder_sweep
and app.services.retention.run_retention_sweep into a background asyncio loop
started at app startup (previously neither sweep was ever invoked outside of
tests). This is a minimal "can be called without exploding" check -- the
underlying sweep functions already have their own thorough test coverage in
tests/test_notify_scheduler.py and tests/test_retention.py -- plus a check
that the startup hook actually schedules the loop as a real asyncio Task.
"""

from __future__ import annotations

from app.db import get_sessionmaker

# NOTE: `app.main` imports at module scope run `app = create_app()`
# immediately (see app/main.py bottom), which needs SECRET_KEY/ENCRYPTION_KEY
# etc. already set -- those are only set by conftest.py's autouse
# `_configure_env` fixture *per test*, not at collection time. Every test
# below imports from app.main lazily (inside the test function, after
# fixtures have run) instead of at the top of this file, same pattern
# tests/conftest.py's own `app` fixture uses.


async def test_run_daily_sweeps_once_does_not_raise_on_empty_db(db_engine):
    from app.main import run_daily_sweeps_once

    # An empty DB (no mail_items/outbound_items at all) is the most common
    # real-world startup state and must not make either sweep blow up.
    await run_daily_sweeps_once(get_sessionmaker())


async def test_run_daily_sweeps_once_survives_one_sweep_failing(db_engine, monkeypatch):
    """Even if the reminder sweep raises, the retention sweep must still run
    (each sweep is independently try/except-wrapped) -- and the coroutine as
    a whole must not raise."""
    from app.main import run_daily_sweeps_once

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated reminder sweep failure")

    monkeypatch.setattr("app.main.run_daily_reminder_sweep", _boom)

    retention_calls = []

    async def _fake_retention(session, *, dry_run=False):
        retention_calls.append(dry_run)
        return {"dry_run": dry_run, "mail_items_processed": 0, "outbound_items_processed": 0}

    monkeypatch.setattr("app.main.run_retention_sweep", _fake_retention)

    await run_daily_sweeps_once(get_sessionmaker())

    assert retention_calls == [False]


async def test_app_startup_schedules_daily_sweep_task(app):
    # `app` fixture (tests/conftest.py) calls create_app(), which fires
    # FastAPI's startup event handlers immediately (TestClient/ASGITransport
    # don't run them automatically the way a real server would, so trigger
    # it explicitly the same way Starlette's own lifespan machinery does).
    async with app.router.lifespan_context(app):
        task = getattr(app.state, "daily_sweep_task", None)
        assert task is not None
        assert not task.done()
        task.cancel()
