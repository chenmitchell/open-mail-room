"""M1-R1 blocking #1: uploads / request bodies must be size-capped rather
than read/decoded unboundedly (CSV import, pickup signature base64, and a
generic ceiling for every other request body)."""

import base64

from app.models.employee import Employee
from app.models.enums import UserRole
from app.security.upload_limits import MAX_CSV_IMPORT_BYTES, MAX_SIGNATURE_PNG_BYTES
from tests._helpers import login_as


async def _make_employee(client, db_session, *, name="王小明", pickup_code="CODE1234"):
    emp = Employee(name=name, aliases=[], pickup_code=pickup_code)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": emp.name, "recipient_employee_id": emp.id},
    )
    assert resp.status_code == 201, resp.text
    return emp, resp.json()["data"]


async def test_csv_import_rejects_oversized_file(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    big_name = "A" * (MAX_CSV_IMPORT_BYTES + 1024)
    csv_content = f"name,aliases,department_code,ext,email,phone\n{big_name},,,,,\n"

    resp = await client.post(
        "/api/v1/employees/import",
        files={"file": ("employees.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


async def test_csv_import_accepts_file_under_the_limit(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    csv_content = "name,aliases,department_code,ext,email,phone\n王小明,,,,,\n"
    resp = await client.post(
        "/api/v1/employees/import",
        files={"file": ("employees.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200


async def test_pickup_signature_rejects_oversized_base64(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    _emp, item = await _make_employee(client, db_session)

    # Not a valid PNG at all, but the size check must reject it before the
    # server ever tries to base64-decode or PNG-validate the payload.
    oversized_b64 = base64.b64encode(b"x" * (MAX_SIGNATURE_PNG_BYTES + 1024)).decode()

    resp = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={
            "method": "signature",
            "picked_up_by_name": "代領人",
            "signature_png_base64": oversized_b64,
        },
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


async def test_global_body_size_limit_rejects_oversized_request_body(client):
    """Defense-in-depth ceiling enforced at the ASGI middleware layer
    (app.security.body_limit) for *any* endpoint -- exercised here without
    even logging in, since the middleware runs ahead of routing/auth."""
    huge_note = "A" * (21 * 1024 * 1024)  # over the 20 MB generic ceiling
    resp = await client.post("/api/v1/items", json={"recipient_name_raw": "x", "note": huge_note})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "UPLOAD_TOO_LARGE"
