"""6-digit LINE/Telegram binding-code issue + verify
(05-NOTIFICATIONS.md section 3)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationChannel
from app.models.notification_binding_code import NotificationBindingCode

CODE_TTL_MINUTES = 10

# M3-R1 blocking #2: the webhook that consumes a code guess has no
# per-employee context to scope a lockout to (any LINE/Telegram user can
# message the shared bot with any 6-digit string), so a wrong guess charges a
# failed attempt against every still-outstanding code for that channel
# instead of against a single row. Once a code's failed_attempts reaches this
# many, it stops matching even though it hasn't expired yet.
MAX_FAILED_ATTEMPTS = 5


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def issue_binding_code(
    session: AsyncSession, *, employee_id: str, channel: NotificationChannel
) -> NotificationBindingCode:
    now = datetime.now(timezone.utc)
    row = NotificationBindingCode(
        employee_id=employee_id,
        channel=channel,
        code=_generate_code(),
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    )
    session.add(row)
    await session.flush()
    return row


async def consume_binding_code(
    session: AsyncSession, *, channel: NotificationChannel, code: str
) -> NotificationBindingCode | None:
    """Looks up an unexpired, unconsumed, not-yet-locked-out code for
    `channel`, marks it consumed, and returns it -- or None if no such code
    exists (wrong code, expired, or invalidated by too many prior wrong
    guesses). Marking-consumed happens here (not by the caller) so a caller
    that goes on to fail for some *other* reason after this call can't
    accidentally leave the code re-usable.

    On a miss, every still-outstanding (unconsumed, unexpired) code for this
    channel has its `failed_attempts` bumped by one (M3-R1 blocking #2): the
    inbound webhook has no way to know which specific code the guess was
    "aimed at", so a brute-force attempt against the whole 10^6 space is
    charged against the shared pool of currently-issued codes rather than
    against nothing. A code whose failed_attempts reaches
    `MAX_FAILED_ATTEMPTS` is excluded from matching from then on (effectively
    invalidated) even before it expires.
    """
    now = datetime.now(timezone.utc)
    stmt = select(NotificationBindingCode).where(
        NotificationBindingCode.channel == channel,
        NotificationBindingCode.code == code,
        NotificationBindingCode.consumed_at.is_(None),
        NotificationBindingCode.expires_at > now,
        NotificationBindingCode.failed_attempts < MAX_FAILED_ATTEMPTS,
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        active_stmt = select(NotificationBindingCode).where(
            NotificationBindingCode.channel == channel,
            NotificationBindingCode.consumed_at.is_(None),
            NotificationBindingCode.expires_at > now,
        )
        active_rows = (await session.execute(active_stmt)).scalars().all()
        for active in active_rows:
            active.failed_attempts += 1
        if active_rows:
            await session.flush()
        return None
    row.consumed_at = now
    await session.flush()
    return row
