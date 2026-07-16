"""GET|POST|PATCH /api/v1/employees, POST /employees/import,
GET /employees/match (02-DATA-MODEL.md `employees`, 01-REQUIREMENTS.md
section 5).

Directory management (create/update/import) is admin-only per the role
table ("admin: ... 員工名錄"); read + fuzzy match are also usable by counter
staff, who need them at OCR-confirmation time.
"""

from __future__ import annotations

import csv
import io
import secrets
import string
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
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
from app.security.rbac import require_role
from app.security.upload_limits import MAX_CSV_IMPORT_BYTES
from app.services.audit import record_audit
from app.services.matching import match_employees
from app.util.csv_safety import sanitize_csv_cell

# M1-R1 blocking #4: CSRF-protect every write on this router in one place
# rather than per-endpoint (GET/HEAD/OPTIONS are exempted inside
# require_csrf itself, so read endpoints are unaffected).
router = APIRouter(prefix="/employees", tags=["employees"], dependencies=[Depends(require_csrf)])

_PICKUP_CODE_ALPHABET = string.ascii_uppercase + string.digits
_PICKUP_CODE_LENGTH = 8

READ_ROLES = (UserRole.admin, UserRole.counter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin,)
MATCH_ROLES = (UserRole.admin, UserRole.counter)


def _serialize(emp: Employee, *, department_name: str | None = None) -> dict[str, Any]:
    """Read-path serializer.

    M1-R1 blocking #3: `pickup_code` is deliberately **not** included here --
    this used to leak every employee's pickup code to any role that could
    read the directory (viewer/counter/admin alike), letting anyone with
    read access impersonate a pickup. The code is now only ever handed back
    once, in the response to the write that (re)generated it -- see
    `_serialize_with_pickup_code` below -- and verified server-side via the
    dedicated `POST /pickup/lookup` endpoint (app/api/v1/pickup.py).

    `department_name` (M1-R1 suggestion) is populated by callers that join
    against `departments`; left `None` otherwise rather than raising, so a
    dangling `department_id` (should one ever occur) doesn't break listing.
    """
    return {
        "id": emp.id,
        "name": emp.name,
        "aliases": emp.aliases or [],
        "department_id": emp.department_id,
        "department_name": department_name,
        "ext": emp.ext,
        "email": emp.email,
        "phone": emp.phone,
        "status": emp.status.value,
        "user_id": emp.user_id,
        "created_at": emp.created_at.isoformat(),
        "updated_at": emp.updated_at.isoformat(),
    }


def _serialize_with_pickup_code(
    emp: Employee, *, department_name: str | None = None
) -> dict[str, Any]:
    """Write-path serializer: same as `_serialize` but includes the current
    `pickup_code`. Only used for the direct response to `POST /employees`
    and `PATCH /employees/{id}` -- i.e. only ever shown to the admin who
    just set/generated that exact code, analogous to how `admin/ai-providers`
    keys are "write-only, shown once" (07-SECURITY.md §2)."""
    return {**_serialize(emp, department_name=department_name), "pickup_code": emp.pickup_code}


async def _department_name(session: AsyncSession, department_id: str | None) -> str | None:
    if department_id is None:
        return None
    dept = await session.get(Department, department_id)
    return dept.name if dept is not None else None


def _generate_pickup_code() -> str:
    return "".join(secrets.choice(_PICKUP_CODE_ALPHABET) for _ in range(_PICKUP_CODE_LENGTH))


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list)
    department_id: str | None = None
    ext: str | None = None
    email: str | None = None
    phone: str | None = None
    status: EmployeeStatus = EmployeeStatus.active
    pickup_code: str | None = None
    user_id: str | None = None


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    aliases: list[str] | None = None
    department_id: str | None = None
    ext: str | None = None
    email: str | None = None
    phone: str | None = None
    status: EmployeeStatus | None = None
    pickup_code: str | None = None
    user_id: str | None = None


async def _get_or_404(session: AsyncSession, employee_id: str) -> Employee:
    emp = await session.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "Employee not found"}
        )
    return emp


async def _validate_department(session: AsyncSession, department_id: str | None) -> None:
    if department_id is None:
        return
    dept = await session.get(Department, department_id)
    if dept is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "DEPARTMENT_NOT_FOUND", "message": "department_id does not exist"},
        )


async def _validate_user(session: AsyncSession, user_id: str | None) -> None:
    """RC-FIX #5: `employees.user_id` links a directory row to a login
    account (auth.py's `_user_public` reads it back for pickup_code/
    department on GET /auth/me); an unvalidated value would silently create
    a dangling FK-less reference to a nonexistent user, same failure shape
    `_validate_department` already guards against for `department_id`."""
    if user_id is None:
        return
    linked_user = await session.get(User, user_id)
    if linked_user is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "USER_NOT_FOUND", "message": "user_id does not exist"},
        )


@router.get("")
async def list_employees(
    pagination: tuple[int, int] = Depends(pagination_params),
    q: str | None = None,
    department_id: str | None = None,
    status: EmployeeStatus | None = None,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*READ_ROLES)),
):
    page, size = pagination
    stmt = select(Employee, Department.name).outerjoin(
        Department, Employee.department_id == Department.id
    )
    count_stmt = select(func.count()).select_from(Employee)

    if q:
        like = f"%{q}%"
        condition = or_(Employee.name.ilike(like))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
        count_stmt = count_stmt.where(Employee.department_id == department_id)
    if status:
        stmt = stmt.where(Employee.status == status)
        count_stmt = count_stmt.where(Employee.status == status)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Employee.name).offset((page - 1) * size).limit(size)
    rows = (await session.execute(stmt)).all()

    return paginated(
        [_serialize(e, department_name=dept_name) for e, dept_name in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/match")
async def match_employees_endpoint(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*MATCH_ROLES)),
):
    matches = await match_employees(session, q, limit=limit)
    return ok(matches)


@router.get("/{employee_id}")
async def get_employee(
    employee_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*READ_ROLES)),
):
    emp = await _get_or_404(session, employee_id)
    dept_name = await _department_name(session, emp.department_id)
    return ok(_serialize(emp, department_name=dept_name))


@router.post("", status_code=201)
async def create_employee(
    payload: EmployeeCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    await _validate_department(session, payload.department_id)
    await _validate_user(session, payload.user_id)

    pickup_code = payload.pickup_code or _generate_pickup_code()
    emp = Employee(
        name=payload.name,
        aliases=payload.aliases,
        department_id=payload.department_id,
        ext=payload.ext,
        email=payload.email,
        phone=payload.phone,
        status=payload.status,
        pickup_code=pickup_code,
        user_id=payload.user_id,
    )
    session.add(emp)

    for _attempt in range(5):
        try:
            await session.flush()
            break
        except IntegrityError as exc:
            await session.rollback()
            if payload.pickup_code:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "PICKUP_CODE_TAKEN",
                        "message": "pickup_code already in use",
                    },
                ) from exc
            # Auto-generated code collided (extremely unlikely) -- retry
            # with a fresh random code rather than failing the request.
            emp.pickup_code = _generate_pickup_code()
            session.add(emp)
    else:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Could not allocate a pickup_code"},
        )

    await record_audit(
        session,
        request=request,
        actor=user,
        action="employee.create",
        target_type="employee",
        target_id=emp.id,
        diff={"after": {**_serialize(emp), "email": None, "phone": None}},
    )
    await session.commit()
    await session.refresh(emp)
    dept_name = await _department_name(session, emp.department_id)
    return ok(_serialize_with_pickup_code(emp, department_name=dept_name))


@router.patch("/{employee_id}")
async def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    emp = await _get_or_404(session, employee_id)
    before = _serialize(emp)

    updates = payload.model_dump(exclude_unset=True)
    if "department_id" in updates:
        await _validate_department(session, updates["department_id"])
    if "user_id" in updates:
        await _validate_user(session, updates["user_id"])

    for field, value in updates.items():
        setattr(emp, field, value)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "PICKUP_CODE_TAKEN", "message": "pickup_code already in use"},
        ) from exc

    after = _serialize(emp)
    await record_audit(
        session,
        request=request,
        actor=user,
        action="employee.update",
        target_type="employee",
        target_id=emp.id,
        diff={
            "before": {**before, "email": None, "phone": None},
            "after": {**after, "email": None, "phone": None},
        },
    )
    await session.commit()
    await session.refresh(emp)
    dept_name = await _department_name(session, emp.department_id)
    return ok(_serialize_with_pickup_code(emp, department_name=dept_name))


async def _read_upload_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read `file` in bounded chunks, aborting with 413 UPLOAD_TOO_LARGE as
    soon as the total exceeds `max_bytes` -- rather than `await file.read()`,
    which loads the entire attacker-controlled upload into memory before any
    size check happens at all (M1-R1 blocking #1)."""
    chunks: list[bytes] = []
    total = 0
    chunk_size = 64 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "UPLOAD_TOO_LARGE",
                    "message": f"CSV file exceeds the {max_bytes} byte limit",
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/import")
async def import_employees(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*WRITE_ROLES)),
):
    raw = await _read_upload_capped(file, MAX_CSV_IMPORT_BYTES)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "UPLOAD_BAD_TYPE", "message": "CSV must be UTF-8 encoded"},
        ) from exc

    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]

    if rows and rows[0] and rows[0][0].strip().lower() == "name":
        rows = rows[1:]

    dept_codes = {row[2].strip() for row in rows if len(row) > 2 and row[2].strip()}
    dept_map: dict[str, Department] = {}
    if dept_codes:
        result = await session.execute(select(Department).where(Department.code.in_(dept_codes)))
        dept_map = {d.code: d for d in result.scalars().all()}

    successes: list[dict] = []
    failures: list[dict] = []

    for idx, row in enumerate(rows, start=1):
        row = [c.strip() for c in row] + [""] * max(0, 6 - len(row))
        name, aliases_raw, department_code, ext, email, phone = row[:6]

        if not name:
            failures.append({"row": idx, "message": "name is required"})
            continue

        department_id = None
        if department_code:
            dept = dept_map.get(department_code)
            if dept is None:
                failures.append(
                    {"row": idx, "message": f"department_code '{department_code}' not found"}
                )
                continue
            department_id = dept.id

        aliases = [a.strip() for a in aliases_raw.split(";") if a.strip()] if aliases_raw else []

        # M1-R1 blocking #2: neutralize CSV formula-injection payloads
        # (leading =/+/-/@) in every free-text cell before it's stored, so
        # a value that entered via CSV import can't later detonate as a
        # formula if pasted into (or exported to) a spreadsheet.
        emp = Employee(
            name=sanitize_csv_cell(name),
            aliases=[sanitize_csv_cell(a) for a in aliases],
            department_id=department_id,
            ext=sanitize_csv_cell(ext) or None,
            email=sanitize_csv_cell(email) or None,
            phone=sanitize_csv_cell(phone) or None,
            status=EmployeeStatus.active,
            pickup_code=_generate_pickup_code(),
        )
        session.add(emp)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            # M1-R1 suggestion: never leak the raw exception (which can
            # include SQL/constraint internals) back to the client.
            failures.append({"row": idx, "message": "database error while saving this row"})
            continue

        successes.append({"row": idx, "employee_id": emp.id})

    if successes:
        await record_audit(
            session,
            request=request,
            actor=user,
            action="employee.import",
            target_type="employee",
            target_id=None,
            diff={"succeeded": len(successes), "failed": len(failures)},
        )
        await session.commit()

    # M1-R1 blocking #7: shape unified to match the documented/frontend
    # contract (frontend/src/types/api.ts EmployeeImportResult) --
    # `{ total, succeeded, failed, errors: [{ row, message }] }` -- rather
    # than the previous ad hoc `success_count`/`failure_count`/`created`/
    # `failures[].error` shape the frontend never actually read.
    return ok(
        {
            "total": len(rows),
            "succeeded": len(successes),
            "failed": len(failures),
            "errors": failures,
        }
    )
