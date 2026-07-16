from app.models.employee import Employee
from app.models.enums import UserRole
from tests._helpers import create_user, login, login_as


async def test_me_items_requires_employee_role(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)

    resp = await client.get("/api/v1/me/items")
    assert resp.status_code == 403


async def test_me_items_empty_when_no_linked_employee(client, db_session):
    await login_as(client, db_session, role=UserRole.employee)

    resp = await client.get("/api/v1/me/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0


async def test_me_items_scoped_to_linked_employee(client, db_session):
    user = await create_user(db_session, email="staff@example.com", role=UserRole.employee)

    emp = Employee(name="王小明", aliases=[], user_id=user.id)
    db_session.add(emp)

    other_emp = Employee(name="陳小華", aliases=[])
    db_session.add(other_emp)
    await db_session.commit()
    await db_session.refresh(emp)
    await db_session.refresh(other_emp)

    # Create items as a counter user for both employees.
    await create_user(db_session, email="counter@example.com", role=UserRole.counter)
    await login(client, email="counter@example.com")

    mine = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": emp.name, "recipient_employee_id": emp.id},
    )
    assert mine.status_code == 201
    await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": other_emp.name, "recipient_employee_id": other_emp.id},
    )

    await login(client, email="staff@example.com")

    resp = await client.get("/api/v1/me/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["recipient_employee_id"] == emp.id


async def test_me_items_status_filter(client, db_session):
    user = await create_user(db_session, email="staff2@example.com", role=UserRole.employee)
    emp = Employee(name="李四", aliases=[], user_id=user.id, pickup_code="ZZZZ9999")
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)

    await create_user(db_session, email="counter2@example.com", role=UserRole.counter)
    await login(client, email="counter2@example.com")
    item = (
        await client.post(
            "/api/v1/items",
            json={"recipient_name_raw": emp.name, "recipient_employee_id": emp.id},
        )
    ).json()["data"]
    await client.post(
        f"/api/v1/items/{item['id']}/pickup",
        json={"method": "pickup_code", "picked_up_by_name": "李四", "pickup_code": "ZZZZ9999"},
    )

    await login(client, email="staff2@example.com")
    resp = await client.get("/api/v1/me/items", params={"status": "picked_up"})
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1

    resp2 = await client.get("/api/v1/me/items", params={"status": "received"})
    assert resp2.json()["meta"]["total"] == 0
