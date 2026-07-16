from app.config import reset_settings_cache
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import UserRole
from app.models.user import User
from app.security.passwords import hash_password


async def _create_user(
    db_session,
    *,
    email="admin@example.com",
    password="Sup3rSecret!",
    role=UserRole.admin,
):
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Test Admin",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def test_login_success(client, db_session):
    await _create_user(db_session, email="ok@example.com", password="Sup3rSecret!")

    resp = await client.post(
        "/api/v1/auth/login", json={"email": "ok@example.com", "password": "Sup3rSecret!"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["email"] == "ok@example.com"
    assert body["data"]["role"] == "admin"
    assert "session" in resp.cookies
    assert "csrf_token" in resp.cookies


async def test_login_fail_wrong_password(client, db_session):
    await _create_user(db_session, email="wrongpw@example.com", password="Sup3rSecret!")

    resp = await client.post(
        "/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "not-the-password"}
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"] == "AUTH_INVALID"


async def test_login_fail_unknown_email(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_INVALID"


async def test_login_lockout(client, db_session):
    await _create_user(db_session, email="lockout@example.com", password="Sup3rSecret!")

    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "lockout@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    # 6th attempt, even with the *correct* password, must be locked out.
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "lockout@example.com", "password": "Sup3rSecret!"},
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "AUTH_RATE_LIMITED"


async def test_login_ip_spray_blocked_across_different_emails(client, db_session):
    """M0-R1 blocking #6: a single IP failing logins against many different
    emails must get rate-limited even though no individual (ip,email) pair
    hit the per-account lockout threshold."""
    await _create_user(db_session, email="spray-target@example.com", password="Sup3rSecret!")

    for i in range(5):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": f"spray{i}@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    # 6th attempt from the same IP, even against a fresh/valid email, must
    # be blocked by the per-IP counter.
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "spray-target@example.com", "password": "Sup3rSecret!"},
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "AUTH_RATE_LIMITED"


async def test_session_cookie_secure_in_production(client, db_session, monkeypatch):
    """M0-R1 blocking #2: with ENVIRONMENT=production (the fail-safe
    default), session/csrf cookies must carry the Secure flag."""
    await _create_user(db_session, email="prod-cookie@example.com", password="Sup3rSecret!")

    monkeypatch.setenv("ENVIRONMENT", "production")
    reset_settings_cache()
    try:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "prod-cookie@example.com", "password": "Sup3rSecret!"},
        )
    finally:
        monkeypatch.setenv("ENVIRONMENT", "development")
        reset_settings_cache()

    assert resp.status_code == 200
    set_cookie_headers = resp.headers.get_list("set-cookie")
    assert set_cookie_headers, "expected Set-Cookie headers on login"
    for header in set_cookie_headers:
        assert "Secure" in header, header


async def test_session_cookie_not_secure_in_development(client, db_session):
    """Sanity check for the flip side: dev cookies stay non-Secure so local
    http://localhost testing keeps working."""
    await _create_user(db_session, email="dev-cookie@example.com", password="Sup3rSecret!")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev-cookie@example.com", "password": "Sup3rSecret!"},
    )
    assert resp.status_code == 200
    set_cookie_headers = resp.headers.get_list("set-cookie")
    assert set_cookie_headers
    for header in set_cookie_headers:
        assert "Secure" not in header, header


async def test_me_requires_session(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_INVALID"


async def test_me_after_login(client, db_session):
    await _create_user(db_session, email="me@example.com", password="Sup3rSecret!")
    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "me@example.com", "password": "Sup3rSecret!"}
    )
    assert login_resp.status_code == 200

    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["email"] == "me@example.com"


async def test_login_and_me_include_pickup_code_for_linked_employee(client, db_session):
    """M3-R1 blocking #5: GET /auth/me (and the login response, same shape)
    must surface the linked employee's pickup_code -- MyMailPage.vue's
    "取件碼大字" has no other way to read it. Also covers the accompanying
    department-name mapping (M3-R1 suggestion)."""
    user = await _create_user(db_session, email="withcode@example.com", password="Sup3rSecret!")
    dept = Department(name="Engineering", code="eng")
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)

    emp = Employee(
        name="王小明", aliases=[], user_id=user.id, pickup_code="ABC12345", department_id=dept.id
    )
    db_session.add(emp)
    await db_session.commit()

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "withcode@example.com", "password": "Sup3rSecret!"}
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["data"]["pickup_code"] == "ABC12345"
    assert login_resp.json()["data"]["department"] == "Engineering"

    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["pickup_code"] == "ABC12345"
    assert me_resp.json()["data"]["department"] == "Engineering"


async def test_me_pickup_code_null_when_no_linked_employee(client, db_session):
    await _create_user(db_session, email="nolink@example.com", password="Sup3rSecret!")
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nolink@example.com", "password": "Sup3rSecret!"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["pickup_code"] is None
    assert resp.json()["data"]["department"] is None


async def test_logout_requires_csrf(client, db_session):
    await _create_user(db_session, email="logout@example.com", password="Sup3rSecret!")
    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "logout@example.com", "password": "Sup3rSecret!"}
    )
    assert login_resp.status_code == 200

    # No/invalid X-CSRF-Token header -> rejected. The test client's
    # conftest.py hook auto-attaches a *valid* token from the session cookie
    # to any request that doesn't already carry the header (mirroring what
    # a real browser + frontend/src/api/client.ts does) -- so to exercise
    # "the header is missing/invalid", explicitly send an empty one rather
    # than omitting it (an omitted header would just get silently filled in
    # by that hook, defeating the point of this test).
    resp = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": ""})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_INVALID"

    csrf_token = login_resp.cookies["csrf_token"]
    resp = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert resp.status_code == 200
    assert resp.json()["data"]["logged_out"] is True


async def test_me_exposes_own_employee_id(client, db_session):
    """M4-R1: without this, a page that needs "who am I as an employee" (the
    outbound applicant) had to fuzzy-match the user's own display name back
    against the directory -- a guess, and an arbitrary one when two employees
    share a name."""
    user = await _create_user(db_session, email="emp@example.com", password="Sup3rSecret!")
    employee = Employee(name=user.display_name, aliases=[], user_id=user.id)
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "emp@example.com", "password": "Sup3rSecret!"}
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["data"]["employee_id"] == employee.id

    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["employee_id"] == employee.id


async def test_me_employee_id_null_without_directory_entry(client, db_session):
    """A counter/admin login with no employees row is normal, not an error."""
    await _create_user(db_session, email="nodir@example.com", password="Sup3rSecret!")
    await client.post(
        "/api/v1/auth/login", json={"email": "nodir@example.com", "password": "Sup3rSecret!"}
    )
    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["employee_id"] is None
