"""Shared test helpers for the M1 (収件核心) endpoint tests. Not itself a
test module (no `test_` prefix) so pytest does not collect it.
"""

from __future__ import annotations

import asyncio

from app.models.enums import UserRole
from app.models.user import User
from app.security.passwords import hash_password


async def create_user(
    db_session,
    *,
    email: str,
    password: str = "Sup3rSecret!",
    role: UserRole = UserRole.admin,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=email.split("@")[0],
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def login(client, *, email: str, password: str = "Sup3rSecret!"):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp


async def login_as(client, db_session, *, role: UserRole, email: str | None = None) -> User:
    email = email or f"{role.value}@example.com"
    user = await create_user(db_session, email=email, role=role)
    await login(client, email=email)
    return user


async def drain_background_ocr_tasks() -> None:
    """Awaits every currently in-flight OCR background task
    (app.ocr.pipeline.run_ocr_job, launched fire-and-forget by
    `POST /ocr/jobs` via `asyncio.create_task`) to completion.

    Call this right after a `POST /ocr/jobs` in a test, *before* issuing any
    further request against the same client -- see app/ocr/pipeline.py's
    module docstring for why: under the test suite's
    `sqlite+aiosqlite:///:memory:` + `StaticPool` setup, a background task's
    session genuinely overlapping in time with a separate request's session
    on that single shared connection can wedge indefinitely instead of
    erroring or serializing. Draining here guarantees the background task's
    session is fully closed before the test's next `client.get(...)` /
    `client.post(...)` opens a new one, so the two are never concurrent.
    """
    # Local import: avoids a hard import-time dependency from this shared
    # test-helpers module on the ocr_jobs router module.
    from app.api.v1.ocr_jobs import _background_tasks

    pending = [task for task in _background_tasks if not task.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def drain_background_notification_tasks() -> None:
    """Same shape/reasoning as `drain_background_ocr_tasks`, for the M3-01
    notification delivery worker (app.notify.worker.launch_delivery /
    launch_delivery_for_many) and the webhook publisher it can chain into on
    a successful `received` delivery (app.webhooks.publisher). Loops until
    no new tasks show up, since delivering a notification can itself spawn a
    further webhook-publish task.
    """
    from app.notify.worker import _background_tasks as notify_tasks
    from app.webhooks.publisher import _background_tasks as webhook_tasks

    while True:
        pending = [t for t in (*notify_tasks, *webhook_tasks) if not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


async def drain_background_webhook_tasks() -> None:
    from app.webhooks.publisher import _background_tasks

    pending = [task for task in _background_tasks if not task.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
