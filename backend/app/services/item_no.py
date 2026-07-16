"""`IN-YYYYMMDD-####` item number allocation.

02-DATA-MODEL.md requires same-day sequential numbering with a unique
constraint on `mail_items.item_no`. Two counter clerks saving at the same
instant is the concurrency case we have to survive: rather than relying on
a database-specific `SELECT ... FOR UPDATE`, which would tie this to
PostgreSQL and defeat the "SQLite/PostgreSQL 皆可跑" requirement in
02-DATA-MODEL.md, we compute a candidate number optimistically and let the
column's UNIQUE constraint be the source of truth -- the caller retries with
the next candidate on an IntegrityError. See `allocate_item_no` docstring
for the retry contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

SEQ_WIDTH = 4


def _date_prefix(prefix: str, when: datetime) -> str:
    return f"{prefix}-{when.strftime('%Y%m%d')}-"


async def next_item_no_candidate(session, *, prefix: str, when: datetime | None = None) -> str:
    """Best-effort next candidate for today's sequence. Not guaranteed to be
    free under concurrent writers -- the caller must catch the unique
    constraint violation on insert and retry (see mail_items router)."""
    from app.models.mail_item import MailItem
    from app.models.outbound_item import OutboundItem

    when = when or datetime.now(timezone.utc)
    day_prefix = _date_prefix(prefix, when)

    model = MailItem if prefix == "IN" else OutboundItem
    result = await session.execute(
        select(func.max(model.item_no)).where(model.item_no.like(f"{day_prefix}%"))
    )
    current_max = result.scalar_one_or_none()

    next_seq = 1
    if current_max:
        try:
            next_seq = int(current_max.rsplit("-", 1)[-1]) + 1
        except ValueError:
            next_seq = 1

    return f"{day_prefix}{next_seq:0{SEQ_WIDTH}d}"


async def allocate_item_no(session, *, prefix: str, when: datetime | None = None) -> str:
    """Convenience alias kept separate from next_item_no_candidate in case
    future callers want allocation without the retry-candidate naming."""
    return await next_item_no_candidate(session, prefix=prefix, when=when)
