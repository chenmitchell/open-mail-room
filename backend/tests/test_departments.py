from app.models.enums import UserRole
from tests._helpers import login_as


async def test_create_department_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post("/api/v1/departments", json={"name": "Sales", "code": "sales"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_create_department_as_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    resp = await client.post("/api/v1/departments", json={"name": "Sales", "code": "sales"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["name"] == "Sales"
    assert body["data"]["code"] == "sales"
    assert body["data"]["is_active"] is True


async def test_create_department_duplicate_code_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    resp1 = await client.post("/api/v1/departments", json={"name": "Sales", "code": "dup"})
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/departments", json={"name": "Other", "code": "dup"})
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "DEPARTMENT_CODE_TAKEN"


async def test_department_hierarchy_parent_id(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    parent_resp = await client.post(
        "/api/v1/departments", json={"name": "Group", "code": "group"}
    )
    parent_id = parent_resp.json()["data"]["id"]

    child_resp = await client.post(
        "/api/v1/departments",
        json={"name": "Sub", "code": "sub", "parent_id": parent_id},
    )
    assert child_resp.status_code == 201
    assert child_resp.json()["data"]["parent_id"] == parent_id


async def test_department_parent_not_found(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    resp = await client.post(
        "/api/v1/departments",
        json={"name": "Sub", "code": "sub2", "parent_id": "does-not-exist"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEPARTMENT_PARENT_NOT_FOUND"


async def test_department_cycle_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    a = (await client.post("/api/v1/departments", json={"name": "A", "code": "a"})).json()["data"]
    b_resp = await client.post(
        "/api/v1/departments", json={"name": "B", "code": "b", "parent_id": a["id"]}
    )
    b = b_resp.json()["data"]

    # Now try to make A's parent be B -> cycle.
    resp = await client.patch(
        f"/api/v1/departments/{a['id']}", json={"parent_id": b["id"]}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "DEPARTMENT_CYCLE"


async def test_update_department_requires_admin(client, db_session):
    admin = await login_as(client, db_session, role=UserRole.admin)
    dept = (
        await client.post("/api/v1/departments", json={"name": "Ops", "code": "ops"})
    ).json()["data"]

    other_client_role = UserRole.viewer
    from tests._helpers import create_user, login

    await create_user(db_session, email="viewer2@example.com", role=other_client_role)
    await login(client, email="viewer2@example.com")

    resp = await client.patch(f"/api/v1/departments/{dept['id']}", json={"name": "Ops2"})
    assert resp.status_code == 403
    assert admin.role == UserRole.admin  # sanity


async def test_list_departments_any_authenticated_role(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)

    resp = await client.get("/api/v1/departments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert "meta" in body
    assert body["meta"]["total"] == 0


async def test_list_departments_requires_auth(client):
    resp = await client.get("/api/v1/departments")
    assert resp.status_code == 401


async def test_patch_rejects_unknown_field(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    dept = (
        await client.post("/api/v1/departments", json={"name": "Fin", "code": "fin"})
    ).json()["data"]

    resp = await client.patch(f"/api/v1/departments/{dept['id']}", json={"bogus_field": 1})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
