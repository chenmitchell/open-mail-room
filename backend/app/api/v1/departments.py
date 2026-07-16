"""GET|POST|PATCH /api/v1/departments (02-DATA-MODEL.md `departments`).

Read is open to any authenticated role; writes are admin-only per
01-REQUIREMENTS.md's role table ("admin: 全部 ... 員工名錄") and the task
brief ("admin 才能寫;階層 parent_id").
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok, paginated
from app.api.v1._common import pagination_params
from app.db import get_session
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeStatus, UserRole
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.rbac import get_current_user, require_role
from app.services.audit import record_audit

# M1-R1 blocking #4: CSRF-protect every write on this router (require_csrf
# is a no-op for GET/HEAD/OPTIONS, so reads are unaffected).
router = APIRouter(
    prefix="/departments", tags=["departments"], dependencies=[Depends(require_csrf)]
)


def _serialize(dept: Department) -> dict[str, Any]:
    return {
        "id": dept.id,
        "name": dept.name,
        "code": dept.code,
        "parent_id": dept.parent_id,
        "manager_employee_id": dept.manager_employee_id,
        "is_active": dept.is_active,
        "created_at": dept.created_at.isoformat(),
        "updated_at": dept.updated_at.isoformat(),
    }


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    parent_id: str | None = None
    manager_employee_id: str | None = None
    is_active: bool = True


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    parent_id: str | None = None
    manager_employee_id: str | None = None
    is_active: bool | None = None


async def _validate_manager(session: AsyncSession, manager_employee_id: str | None) -> None:
    """A department's contact (manager_employee_id) must be an existing, active
    employee -- a 部門件 routed to a bogus/inactive contact would silently go
    nowhere. Mirrors the defensive check on the OCR-candidate path."""
    if manager_employee_id is None:
        return
    emp = await session.get(Employee, manager_employee_id)
    if emp is None or emp.status != EmployeeStatus.active:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MANAGER_NOT_FOUND",
                "message": "manager_employee_id must be an existing, active employee",
            },
        )


async def _get_or_404(session: AsyncSession, department_id: str) -> Department:
    dept = await session.get(Department, department_id)
    if dept is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Department not found"},
        )
    return dept


async def _assert_no_cycle(session: AsyncSession, *, department_id: str, parent_id: str) -> None:
    if parent_id == department_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "DEPARTMENT_CYCLE", "message": "A department cannot be its own parent"},
        )
    current = await session.get(Department, parent_id)
    if current is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "DEPARTMENT_PARENT_NOT_FOUND", "message": "parent_id does not exist"},
        )
    seen = {department_id}
    while current is not None and current.parent_id:
        if current.parent_id == department_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "DEPARTMENT_CYCLE",
                    "message": "parent_id would create a cycle in the department hierarchy",
                },
            )
        if current.parent_id in seen:
            # Pre-existing cycle unrelated to this update -- stop walking
            # rather than looping forever.
            break
        seen.add(current.id)
        current = await session.get(Department, current.parent_id)


@router.get("")
async def list_departments(
    pagination: tuple[int, int] = Depends(pagination_params),
    is_active: bool | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    page, size = pagination
    stmt = select(Department)
    count_stmt = select(func.count()).select_from(Department)
    if is_active is not None:
        stmt = stmt.where(Department.is_active == is_active)
        count_stmt = count_stmt.where(Department.is_active == is_active)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Department.name).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).scalars().all()

    return paginated([_serialize(d) for d in rows], total=total, page=page, size=size)


@router.get("/{department_id}")
async def get_department(
    department_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    dept = await _get_or_404(session, department_id)
    return ok(_serialize(dept))


@router.post("", status_code=201)
async def create_department(
    payload: DepartmentCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(UserRole.admin)),
):
    if payload.parent_id is not None:
        parent = await session.get(Department, payload.parent_id)
        if parent is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "DEPARTMENT_PARENT_NOT_FOUND",
                    "message": "parent_id does not exist",
                },
            )

    await _validate_manager(session, payload.manager_employee_id)

    dept = Department(
        name=payload.name,
        code=payload.code,
        parent_id=payload.parent_id,
        manager_employee_id=payload.manager_employee_id,
        is_active=payload.is_active,
    )
    session.add(dept)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "DEPARTMENT_CODE_TAKEN", "message": "code already in use"},
        ) from exc

    await record_audit(
        session,
        request=request,
        actor=user,
        action="department.create",
        target_type="department",
        target_id=dept.id,
        diff={"after": _serialize(dept)},
    )
    await session.commit()
    await session.refresh(dept)
    return ok(_serialize(dept))


@router.patch("/{department_id}")
async def update_department(
    department_id: str,
    payload: DepartmentUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(UserRole.admin)),
):
    dept = await _get_or_404(session, department_id)
    before = _serialize(dept)

    updates = payload.model_dump(exclude_unset=True)
    if "manager_employee_id" in updates:
        await _validate_manager(session, updates["manager_employee_id"])
    if "parent_id" in updates and updates["parent_id"] is not None:
        await _assert_no_cycle(session, department_id=department_id, parent_id=updates["parent_id"])

    for field, value in updates.items():
        setattr(dept, field, value)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "DEPARTMENT_CODE_TAKEN", "message": "code already in use"},
        ) from exc

    await record_audit(
        session,
        request=request,
        actor=user,
        action="department.update",
        target_type="department",
        target_id=dept.id,
        diff={"before": before, "after": _serialize(dept)},
    )
    await session.commit()
    await session.refresh(dept)
    return ok(_serialize(dept))
