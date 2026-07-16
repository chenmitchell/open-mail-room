"""POST /api/v1/pickup/lookup -- M1-R1 blocking #3 / suggestions:
dedicated, server-side-verified pickup-code lookup that replaces the
never-worked `GET /employees?q=<code>` flow, and no longer leaks
`pickup_code` through `GET /employees` (see also tests/test_employees.py).
"""

from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import UserRole
from tests._helpers import login_as


async def _make_department(db_session, code="eng") -> Department:
    dept = Department(name="Engineering", code=code)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


async def _make_employee(
    db_session, *, name="王小明", pickup_code="CODE1234", department_id=None
) -> Employee:
    emp = Employee(name=name, aliases=[], pickup_code=pickup_code, department_id=department_id)
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


async def _create_item(client, *, recipient_employee_id, recipient_name_raw):
    resp = await client.post(
        "/api/v1/items",
        json={
            "recipient_name_raw": recipient_name_raw,
            "recipient_employee_id": recipient_employee_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_pickup_lookup_requires_counter_or_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)
    resp = await client.post("/api/v1/pickup/lookup", json={"pickup_code": "CODE1234"})
    assert resp.status_code == 403


async def test_pickup_lookup_success_returns_employee_and_pending_items(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    dept = await _make_department(db_session)
    emp = await _make_employee(db_session, department_id=dept.id)
    item = await _create_item(client, recipient_employee_id=emp.id, recipient_name_raw=emp.name)

    resp = await client.post("/api/v1/pickup/lookup", json={"pickup_code": "CODE1234"})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["employee"]["id"] == emp.id
    assert body["employee"]["name"] == emp.name
    assert body["employee"]["department_name"] == "Engineering"
    # M1-R1 blocking #3: the employee sub-object must never carry the code itself.
    assert "pickup_code" not in body["employee"]
    assert [i["id"] for i in body["items"]] == [item["id"]]


async def test_pickup_lookup_wrong_code_rejected_and_counted(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    await _make_employee(db_session)

    resp = await client.post("/api/v1/pickup/lookup", json={"pickup_code": "WRONGCODE"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PICKUP_CODE_INVALID"


async def test_pickup_lookup_rate_limited_after_repeated_failures(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    await _make_employee(db_session)

    for _ in range(5):
        resp = await client.post("/api/v1/pickup/lookup", json={"pickup_code": "WRONGCODE"})
        assert resp.status_code == 422

    resp = await client.post("/api/v1/pickup/lookup", json={"pickup_code": "WRONGCODE"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "PICKUP_CODE_RATE_LIMITED"

    # A *different* code from the same IP is unaffected -- it's the
    # per-(ip,code) counter that's exhausted here, not the (much higher)
    # per-IP sweep counter exercised by the next test below.
    resp2 = await client.post("/api/v1/pickup/lookup", json={"pickup_code": "CODE1234"})
    assert resp2.status_code == 200


async def test_pickup_lookup_ip_wide_lockout_blocks_even_a_fresh_code(client, db_session):
    """The per-IP counter (20 failed attempts/15min, regardless of which
    code) exists specifically to stop an attacker sweeping through many
    *different* codes fast enough to dodge the per-code counter above."""
    await login_as(client, db_session, role=UserRole.counter)
    await _make_employee(db_session)

    for i in range(20):
        resp = await client.post("/api/v1/pickup/lookup", json={"pickup_code": f"WRONG{i:03d}"})
        assert resp.status_code == 422

    resp = await client.post("/api/v1/pickup/lookup", json={"pickup_code": "CODE1234"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "PICKUP_CODE_RATE_LIMITED"


async def test_pickup_lookup_only_returns_active_status_items(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    emp = await _make_employee(db_session)
    item = await _create_item(client, recipient_employee_id=emp.id, recipient_name_raw=emp.name)

    picked = await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "王小明", "pickup_code": "CODE1234"},
    )
    assert picked.status_code == 200

    resp = await client.post("/api/v1/pickup/lookup", json={"pickup_code": "CODE1234"})
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []
