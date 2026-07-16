"""SETUP-WIZARD: GET /api/v1/setup/status + POST /api/v1/setup, the
first-run "create the initial administrator" flow that replaces
scripts/seed.py auto-generating an admin with a random password printed to
the deploy log.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.enums import UserRole
from app.models.user import User
from app.security.rate_limit import get_setup_rate_limiter
from tests._helpers import create_user


async def test_status_reports_needs_setup_true_when_no_admin(client):
    resp = await client.get("/api/v1/setup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["needs_setup"] is True


async def test_status_reports_needs_setup_false_once_admin_exists(client, db_session):
    await create_user(db_session, email="existing-admin@example.com", role=UserRole.admin)

    resp = await client.get("/api/v1/setup/status")
    assert resp.status_code == 200
    assert resp.json()["data"]["needs_setup"] is False


async def test_status_ignores_non_admin_users(client, db_session):
    # A viewer/counter/employee account existing must not count as "setup
    # done" -- the gate is specifically "no admin exists yet".
    await create_user(db_session, email="just-a-viewer@example.com", role=UserRole.viewer)

    resp = await client.get("/api/v1/setup/status")
    assert resp.status_code == 200
    assert resp.json()["data"]["needs_setup"] is True


async def test_post_setup_creates_first_admin_and_it_can_log_in(client, db_session):
    resp = await client.post(
        "/api/v1/setup",
        json={
            "email": "New-Admin@Example.com",
            "display_name": "First Admin",
            "password": "Sup3rSecretAdmin!",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["ok"] is True

    # Does NOT auto-login: no session cookie set on this response.
    assert "session" not in resp.cookies

    # Email is normalized (stripped + lowercased), same convention as login.
    result = await db_session.execute(
        select(User).where(User.email == "new-admin@example.com")
    )
    user = result.scalar_one()
    assert user.role == UserRole.admin
    assert user.display_name == "First Admin"

    # The freshly created admin can log in with the password they chose.
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "new-admin@example.com", "password": "Sup3rSecretAdmin!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert login_resp.json()["data"]["role"] == "admin"

    # setup/status now reports the wizard is done.
    status_resp = await client.get("/api/v1/setup/status")
    assert status_resp.json()["data"]["needs_setup"] is False


async def test_post_setup_writes_system_audit_log(client, db_session):
    from app.models.audit_log import AuditLog

    resp = await client.post(
        "/api/v1/setup",
        json={
            "email": "audit-admin@example.com",
            "display_name": "Audit Admin",
            "password": "Sup3rSecretAdmin!",
        },
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "setup.create_admin")
    )
    entry = result.scalar_one()
    assert entry.actor_type.value == "system"
    assert entry.actor_id is None
    assert entry.target_type == "user"


async def test_post_setup_second_time_returns_409(client, db_session):
    first = await client.post(
        "/api/v1/setup",
        json={
            "email": "first-admin@example.com",
            "display_name": "First Admin",
            "password": "Sup3rSecretAdmin!",
        },
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/setup",
        json={
            "email": "second-admin@example.com",
            "display_name": "Second Admin",
            "password": "AnotherSecret!123",
        },
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "SETUP_ALREADY_DONE"

    # The second attempt must not have created a user.
    result = await db_session.execute(
        select(User).where(User.email == "second-admin@example.com")
    )
    assert result.scalar_one_or_none() is None


async def test_post_setup_rejects_when_admin_already_exists_via_db(client, db_session):
    """Same 409, but the admin was created out-of-band (e.g. the opt-in
    ADMIN_EMAIL/ADMIN_PASSWORD seed path) rather than through this
    endpoint."""
    await create_user(db_session, email="seeded-admin@example.com", role=UserRole.admin)

    resp = await client.post(
        "/api/v1/setup",
        json={
            "email": "wont-be-created@example.com",
            "display_name": "Nope",
            "password": "Sup3rSecretAdmin!",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SETUP_ALREADY_DONE"


async def test_post_setup_rejects_too_short_password(client, db_session):
    resp = await client.post(
        "/api/v1/setup",
        json={
            "email": "weak-pw@example.com",
            "display_name": "Weak Password",
            "password": "short1",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PASSWORD_TOO_WEAK"

    result = await db_session.execute(select(User).where(User.email == "weak-pw@example.com"))
    assert result.scalar_one_or_none() is None


async def test_post_setup_rejects_malformed_email(client):
    resp = await client.post(
        "/api/v1/setup",
        json={
            "email": "not-an-email",
            "display_name": "Bad Email",
            "password": "Sup3rSecretAdmin!",
        },
    )
    assert resp.status_code == 422


async def test_post_setup_does_not_require_csrf_header(client):
    """Bootstrap endpoint: no session/csrf cookie exists yet, so (like
    /auth/login) it must work with no X-CSRF-Token header at all."""
    resp = await client.post(
        "/api/v1/setup",
        json={
            "email": "no-csrf-admin@example.com",
            "display_name": "No Csrf",
            "password": "Sup3rSecretAdmin!",
        },
        headers={"X-CSRF-Token": ""},
    )
    assert resp.status_code == 200, resp.text


async def test_post_setup_rate_limited_per_ip(client, db_session):
    limiter = get_setup_rate_limiter()
    # Exhaust the limiter directly (mirrors test_login.py's lockout tests'
    # style of driving the same rate limiter the endpoint itself uses,
    # avoids a 10-request-long test for the default max_attempts=10).
    for _ in range(limiter.max_attempts):
        limiter.record_failure("127.0.0.1")

    resp = await client.post(
        "/api/v1/setup",
        json={
            "email": "rate-limited-admin@example.com",
            "display_name": "Rate Limited",
            "password": "Sup3rSecretAdmin!",
        },
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "SETUP_RATE_LIMITED"

    result = await db_session.execute(
        select(User).where(User.email == "rate-limited-admin@example.com")
    )
    assert result.scalar_one_or_none() is None
