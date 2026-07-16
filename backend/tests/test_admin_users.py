"""M7-USERS: GET|POST|PATCH /api/v1/admin/users,
POST /admin/users/{id}/reset-password -- admin-only login-account
management, the normal (non-bootstrap) path for creating accounts once
`POST /api/v1/setup` (app/api/v1/setup.py) has locked itself after the
first admin.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.employee import Employee
from app.models.enums import UserRole
from tests._helpers import create_user, login, login_as


async def _make_employee(db_session, *, name: str = "王小明") -> Employee:
    emp = Employee(name=name, aliases=[])
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp


# ---------------------------------------------------------------------------
# POST /admin/users
# ---------------------------------------------------------------------------


async def test_create_user_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "new@example.com",
            "display_name": "New Person",
            "role": "viewer",
            "password": "Sup3rSecret!",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_create_user_each_role_succeeds(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    for role in ("admin", "counter", "employee", "viewer"):
        resp = await client.post(
            "/api/v1/admin/users",
            json={
                "email": f"{role}-user@example.com",
                "display_name": f"{role} user",
                "role": role,
                "password": "Sup3rSecret!",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["role"] == role
        assert body["email"] == f"{role}-user@example.com"
        assert body["is_active"] is True
        assert "password" not in body
        assert "password_hash" not in body
        assert "totp_secret" not in body


async def test_create_user_duplicate_email_conflicts(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    await create_user(db_session, email="dupe@example.com", role=UserRole.viewer)

    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "dupe@example.com",
            "display_name": "Dupe",
            "role": "viewer",
            "password": "Sup3rSecret!",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_EXISTS"


async def test_create_user_weak_password_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "weak@example.com",
            "display_name": "Weak",
            "role": "viewer",
            "password": "short1",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WEAK_PASSWORD"


async def test_create_user_bad_employee_id_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "linked@example.com",
            "display_name": "Linked",
            "role": "employee",
            "password": "Sup3rSecret!",
            "employee_id": "nope",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPLOYEE_NOT_FOUND"


async def test_create_user_links_employee(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    emp = await _make_employee(db_session)

    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "linked2@example.com",
            "display_name": "Linked Two",
            "role": "employee",
            "password": "Sup3rSecret!",
            "employee_id": emp.id,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["employee_id"] == emp.id
    assert body["employee_name"] == emp.name

    await db_session.refresh(emp)
    assert emp.user_id == body["id"]


async def test_create_user_writes_audit_log(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    from app.models.audit_log import AuditLog

    resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "audited@example.com",
            "display_name": "Audited",
            "role": "viewer",
            "password": "Sup3rSecret!",
        },
    )
    assert resp.status_code == 201

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "user.create")
    )
    entry = result.scalar_one()
    assert entry.target_type == "user"


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------


async def test_list_users_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 403


async def test_list_users_paginated_and_masked(client, db_session):
    admin = await login_as(client, db_session, role=UserRole.admin)
    await create_user(db_session, email="other@example.com", role=UserRole.viewer)

    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["meta"]["total"] == 2
    emails = {row["email"] for row in body["data"]}
    assert emails == {admin.email, "other@example.com"}
    for row in body["data"]:
        assert "password_hash" not in row
        assert "totp_secret" not in row


# ---------------------------------------------------------------------------
# PATCH /admin/users/{id}
# ---------------------------------------------------------------------------


async def test_update_user_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    target = await create_user(db_session, email="target@example.com", role=UserRole.viewer)

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}", json={"display_name": "Renamed"}
    )
    assert resp.status_code == 403


async def test_update_user_not_found(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.patch("/api/v1/admin/users/does-not-exist", json={"display_name": "X"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_update_user_changes_role_and_active(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    target = await create_user(db_session, email="target2@example.com", role=UserRole.viewer)

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"role": "counter", "display_name": "Renamed Person"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["role"] == "counter"
    assert body["display_name"] == "Renamed Person"


async def test_update_user_last_admin_cannot_be_demoted(client, db_session):
    admin = await login_as(client, db_session, role=UserRole.admin)

    resp = await client.patch(f"/api/v1/admin/users/{admin.id}", json={"role": "viewer"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LAST_ADMIN"


async def test_update_user_last_admin_cannot_be_deactivated(client, db_session):
    admin = await login_as(client, db_session, role=UserRole.admin)

    resp = await client.patch(f"/api/v1/admin/users/{admin.id}", json={"is_active": False})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "LAST_ADMIN"


async def test_update_user_demote_allowed_when_another_admin_active(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    second_admin = await create_user(
        db_session, email="second-admin@example.com", role=UserRole.admin
    )

    resp = await client.patch(
        f"/api/v1/admin/users/{second_admin.id}", json={"role": "viewer"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["role"] == "viewer"


async def test_update_user_links_and_unlinks_employee(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    target = await create_user(db_session, email="linkable@example.com", role=UserRole.employee)
    emp = await _make_employee(db_session)

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}", json={"employee_id": emp.id}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["employee_id"] == emp.id

    resp2 = await client.patch(
        f"/api/v1/admin/users/{target.id}", json={"employee_id": None}
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["data"]["employee_id"] is None

    await db_session.refresh(emp)
    assert emp.user_id is None


async def test_update_user_bad_employee_id_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    target = await create_user(db_session, email="linkable2@example.com", role=UserRole.employee)

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}", json={"employee_id": "nope"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPLOYEE_NOT_FOUND"


# ---------------------------------------------------------------------------
# POST /admin/users/{id}/reset-password
# ---------------------------------------------------------------------------


async def test_reset_password_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    target = await create_user(db_session, email="resettarget@example.com", role=UserRole.viewer)

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/reset-password",
        json={"new_password": "Sup3rSecret!2"},
    )
    assert resp.status_code == 403


async def test_reset_password_weak_rejected(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    target = await create_user(db_session, email="resettarget2@example.com", role=UserRole.viewer)

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/reset-password", json={"new_password": "short"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WEAK_PASSWORD"


async def test_reset_password_success_and_login_with_new_password(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    target = await create_user(
        db_session,
        email="resettarget3@example.com",
        role=UserRole.viewer,
        password="OldPassword1!",
    )

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/reset-password",
        json={"new_password": "BrandNewPassword1!"},
    )
    assert resp.status_code == 200, resp.text
    assert "password" not in resp.json()["data"]

    login_resp = await client.post(
        "/api/v1/auth/logout",
    )
    assert login_resp.status_code == 200

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "resettarget3@example.com", "password": "BrandNewPassword1!"},
    )
    assert login_resp.status_code == 200, login_resp.text


# ---------------------------------------------------------------------------
# POST /me/password (self-service, any role)
# ---------------------------------------------------------------------------


async def test_change_own_password_requires_current_password(client, db_session):
    await create_user(db_session, email="self@example.com", role=UserRole.viewer)
    await login(client, email="self@example.com")

    resp = await client.post(
        "/api/v1/me/password",
        json={"current_password": "WrongPassword!", "new_password": "NewPassword1!"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CURRENT_PASSWORD_INVALID"


async def test_change_own_password_weak_new_password_rejected(client, db_session):
    await create_user(db_session, email="self2@example.com", role=UserRole.viewer)
    await login(client, email="self2@example.com")

    resp = await client.post(
        "/api/v1/me/password",
        json={"current_password": "Sup3rSecret!", "new_password": "short"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WEAK_PASSWORD"


async def test_change_own_password_success(client, db_session):
    await create_user(db_session, email="self3@example.com", role=UserRole.employee)
    await login(client, email="self3@example.com")

    resp = await client.post(
        "/api/v1/me/password",
        json={"current_password": "Sup3rSecret!", "new_password": "BrandNewPassword1!"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["ok"] is True

    await client.post("/api/v1/auth/logout")

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "self3@example.com", "password": "BrandNewPassword1!"},
    )
    assert login_resp.status_code == 200, login_resp.text


async def test_change_own_password_writes_audit_log(client, db_session):
    user = await create_user(db_session, email="self4@example.com", role=UserRole.viewer)
    await login(client, email="self4@example.com")

    from app.models.audit_log import AuditLog

    resp = await client.post(
        "/api/v1/me/password",
        json={"current_password": "Sup3rSecret!", "new_password": "BrandNewPassword1!"},
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "user.change_own_password")
    )
    entry = result.scalar_one()
    assert entry.actor_id == user.id


async def test_change_own_password_requires_csrf(client, db_session):
    await create_user(db_session, email="self5@example.com", role=UserRole.viewer)
    await login(client, email="self5@example.com")

    resp = await client.post(
        "/api/v1/me/password",
        json={"current_password": "Sup3rSecret!", "new_password": "BrandNewPassword1!"},
        headers={"x-csrf-token": "wrong-token"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_INVALID"
