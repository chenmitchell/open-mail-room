"""GET /api/v1/exports/items.csv, GET /api/v1/exports/outbound.csv --
streaming, formula-injection escaping, UTF-8 BOM, confidentiality carve-out
(01-REQUIREMENTS.md section 4 "匯出 CSV")."""

from __future__ import annotations

import csv
import io

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import UserRole
from tests._helpers import create_user, login, login_as


async def test_items_csv_requires_read_role(client, db_session):
    await create_user(db_session, email="empz@example.com", role=UserRole.employee)
    await login(client, email="empz@example.com")
    resp = await client.get("/api/v1/exports/items.csv")
    assert resp.status_code == 403


async def test_items_csv_has_bom_and_header(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.get("/api/v1/exports/items.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.text.startswith("﻿")
    body_without_bom = resp.text[1:]
    header_line = body_without_bom.splitlines()[0]
    assert header_line.split(",")[0] == "item_no"


async def test_items_csv_escapes_formula_injection(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "王小明", "sender_name": "=cmd|'/c calc'!A1"},
    )
    assert resp.status_code == 201

    export_resp = await client.get("/api/v1/exports/items.csv")
    assert export_resp.status_code == 200
    body_without_bom = export_resp.text[1:]
    reader = csv.reader(io.StringIO(body_without_bom))
    rows = list(reader)
    header, data_row = rows[0], rows[1]
    sender_idx = header.index("sender_name")
    # sanitize_csv_cell prefixes a leading single quote to neutralize the
    # formula trigger -- the raw value must never reach the cell unescaped.
    assert data_row[sender_idx] == "'=cmd|'/c calc'!A1"


async def test_items_csv_excludes_confidential_for_viewer(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "機密", "is_confidential": True, "sender_name": "秘密寄件人"},
    )
    assert resp.status_code == 201

    await login_as(client, db_session, role=UserRole.viewer, email="viewer1@example.com")
    export_resp = await client.get("/api/v1/exports/items.csv")
    assert export_resp.status_code == 200
    assert "秘密寄件人" not in export_resp.text
    assert "機密" not in export_resp.text


async def test_items_csv_includes_confidential_for_admin_and_audits(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/items",
        json={
            "recipient_name_raw": "機密件",
            "is_confidential": True,
            "sender_name": "秘密寄件人A",
        },
    )
    assert resp.status_code == 201

    await login_as(client, db_session, role=UserRole.admin, email="admin-export@example.com")
    export_resp = await client.get("/api/v1/exports/items.csv")
    assert export_resp.status_code == 200
    assert "秘密寄件人A" in export_resp.text

    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "mail_item.export_csv")
    )
    rows = result.scalars().all()
    assert len(rows) == 1


async def test_outbound_csv_basic(client, db_session):
    dept = Department(name="部門X", code="dept-x")
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    emp = Employee(name="申請人", aliases=[], department_id=dept.id)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)

    await login_as(client, db_session, role=UserRole.admin, email="admin-outcsv@example.com")
    created = (
        await client.post(
            "/api/v1/outbound",
            json={"applicant_employee_id": emp.id, "department_id": dept.id, "to_name": "收件方"},
        )
    ).json()["data"]
    await client.post(f"/api/v1/outbound/{created['id']}/shipped", json={"tracking_no": "OUTTRK1"})

    resp = await client.get("/api/v1/exports/outbound.csv")
    assert resp.status_code == 200
    assert resp.text.startswith("﻿")
    body_without_bom = resp.text[1:]
    reader = csv.reader(io.StringIO(body_without_bom))
    rows = list(reader)
    header, data_row = rows[0], rows[1]
    assert data_row[header.index("applicant_name")] == "申請人"
    assert data_row[header.index("department")] == "部門X"
    assert data_row[header.index("to_name")] == "收件方"
    assert data_row[header.index("tracking_no")] == "OUTTRK1"
    assert data_row[header.index("status")] == "shipped"
