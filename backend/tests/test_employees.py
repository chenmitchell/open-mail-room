from app.models.department import Department
from app.models.enums import UserRole
from tests._helpers import login_as


async def _make_department(db_session, code="eng") -> Department:
    dept = Department(name="Engineering", code=code)
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


async def test_create_employee_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post("/api/v1/employees", json={"name": "王小明"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_create_employee_as_admin_auto_generates_pickup_code(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    resp = await client.post(
        "/api/v1/employees",
        json={"name": "王小明", "aliases": ["David Wang"], "email": "david@example.com"},
    )
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["name"] == "王小明"
    assert body["aliases"] == ["David Wang"]
    assert body["email"] == "david@example.com"
    assert body["pickup_code"] and len(body["pickup_code"]) == 8
    assert body["status"] == "active"


async def test_create_employee_with_department(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    dept = await _make_department(db_session)

    resp = await client.post("/api/v1/employees", json={"name": "陳小華", "department_id": dept.id})
    assert resp.status_code == 201
    assert resp.json()["data"]["department_id"] == dept.id


async def test_create_employee_bad_department_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    resp = await client.post("/api/v1/employees", json={"name": "X", "department_id": "nope"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEPARTMENT_NOT_FOUND"


async def test_create_employee_bad_user_id_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    resp = await client.post("/api/v1/employees", json={"name": "X", "user_id": "nope"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_create_employee_with_valid_user_id(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    from tests._helpers import create_user

    linked_user = await create_user(db_session, email="linked1@example.com", role=UserRole.employee)

    resp = await client.post(
        "/api/v1/employees", json={"name": "王小明", "user_id": linked_user.id}
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["user_id"] == linked_user.id


async def test_update_employee_bad_user_id_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    emp = (await client.post("/api/v1/employees", json={"name": "Y3"})).json()["data"]

    resp = await client.patch(f"/api/v1/employees/{emp['id']}", json={"user_id": "nope"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_update_employee_with_valid_user_id(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    emp = (await client.post("/api/v1/employees", json={"name": "Y4"})).json()["data"]

    from tests._helpers import create_user

    linked_user = await create_user(db_session, email="linked2@example.com", role=UserRole.employee)

    resp = await client.patch(
        f"/api/v1/employees/{emp['id']}", json={"user_id": linked_user.id}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["user_id"] == linked_user.id


async def test_list_employees_viewer_can_read(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)

    resp = await client.get("/api/v1/employees")
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 0


async def test_list_employees_employee_role_forbidden(client, db_session):
    await login_as(client, db_session, role=UserRole.employee)

    resp = await client.get("/api/v1/employees")
    assert resp.status_code == 403


async def test_update_employee_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    emp = (await client.post("/api/v1/employees", json={"name": "Y"})).json()["data"]

    from tests._helpers import create_user, login

    await create_user(db_session, email="counter2@example.com", role=UserRole.counter)
    await login(client, email="counter2@example.com")

    resp = await client.patch(f"/api/v1/employees/{emp['id']}", json={"name": "Y2"})
    assert resp.status_code == 403


async def test_update_employee_patch_status(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    emp = (await client.post("/api/v1/employees", json={"name": "Z"})).json()["data"]

    resp = await client.patch(f"/api/v1/employees/{emp['id']}", json={"status": "inactive"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "inactive"


async def test_update_employee_rejects_unknown_field(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    emp = (await client.post("/api/v1/employees", json={"name": "Z2"})).json()["data"]

    resp = await client.patch(f"/api/v1/employees/{emp['id']}", json={"nope": 1})
    assert resp.status_code == 422


async def test_list_and_get_employee_never_expose_pickup_code(client, db_session):
    """M1-R1 blocking #3: pickup_code used to leak through GET /employees to
    every read role (viewer/counter/admin alike). Read responses must never
    include the key at all, regardless of who's asking."""
    await login_as(client, db_session, role=UserRole.admin)
    created = (await client.post("/api/v1/employees", json={"name": "王小明"})).json()["data"]
    assert created["pickup_code"]  # the create response is the one legitimate exception

    for role in (UserRole.admin, UserRole.counter, UserRole.viewer):
        await create_user_and_login(client, db_session, role=role)

        list_resp = await client.get("/api/v1/employees")
        assert list_resp.status_code == 200
        for emp in list_resp.json()["data"]:
            assert "pickup_code" not in emp

        get_resp = await client.get(f"/api/v1/employees/{created['id']}")
        assert get_resp.status_code == 200
        assert "pickup_code" not in get_resp.json()["data"]


async def create_user_and_login(client, db_session, *, role):
    from tests._helpers import create_user, login

    email = f"read-{role.value}@example.com"
    await create_user(db_session, email=email, role=role)
    await login(client, email=email)


async def test_update_employee_response_includes_regenerated_pickup_code(client, db_session):
    """The write-path response (create/update) is the one place pickup_code
    is still returned -- the admin who just (re)generated it needs to see it
    once to hand it to the employee."""
    await login_as(client, db_session, role=UserRole.admin)
    emp = (await client.post("/api/v1/employees", json={"name": "Z3"})).json()["data"]

    resp = await client.patch(f"/api/v1/employees/{emp['id']}", json={"pickup_code": "NEWCODE9"})
    assert resp.status_code == 200
    assert resp.json()["data"]["pickup_code"] == "NEWCODE9"


async def test_pickup_code_uniqueness_enforced(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    first = await client.post("/api/v1/employees", json={"name": "A", "pickup_code": "ABCD1234"})
    assert first.status_code == 201

    second = await client.post("/api/v1/employees", json={"name": "B", "pickup_code": "ABCD1234"})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "PICKUP_CODE_TAKEN"
