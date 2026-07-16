"""GET /api/v1/carriers (02-DATA-MODEL.md `carriers`, seeded by
scripts/seed.py). M1-R1 blocking #6: the frontend's manual-registration
carrier dropdown (frontend/src/api/carriers.ts, InboundRegisterPage.vue)
has always called this endpoint, but the backend never implemented it --
so the dropdown silently rendered empty. Read-only for now (no admin CRUD
endpoint is requested by this milestone); any authenticated role may read,
matching the sibling `GET /departments` endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import paginated
from app.api.v1._common import pagination_params
from app.db import get_session
from app.models.carrier import Carrier
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.rbac import get_current_user

router = APIRouter(prefix="/carriers", tags=["carriers"], dependencies=[Depends(require_csrf)])


def _serialize(carrier: Carrier) -> dict[str, Any]:
    return {
        "id": carrier.id,
        "name": carrier.name,
        "slug": carrier.slug,
        "kind": carrier.kind.value,
        "tracking_pattern": carrier.tracking_pattern,
        "is_active": carrier.is_active,
    }


@router.get("")
async def list_carriers(
    pagination: tuple[int, int] = Depends(pagination_params),
    q: str | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    page, size = pagination
    stmt = select(Carrier)
    count_stmt = select(func.count()).select_from(Carrier)

    if q:
        condition = Carrier.name.ilike(f"%{q}%")
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    if is_active is not None:
        stmt = stmt.where(Carrier.is_active == is_active)
        count_stmt = count_stmt.where(Carrier.is_active == is_active)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Carrier.name).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).scalars().all()

    return paginated([_serialize(c) for c in rows], total=total, page=page, size=size)
