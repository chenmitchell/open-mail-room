"""M1-R1 blocking #4: every write endpoint (not just /logout) must reject a
missing/mismatched CSRF token. The `client` fixture (tests/conftest.py)
auto-attaches a valid `X-CSRF-Token` header from the session cookie on every
non-safe-method request -- mirroring frontend/src/api/client.ts -- so the
~80 other tests in this suite that never mention CSRF explicitly are
implicitly exercising the "valid token accepted" side of this on every
request they make. These tests cover the "invalid/missing token rejected"
side directly.
"""

from fastapi import HTTPException, Request

from app.models.enums import UserRole
from app.security.csrf import require_csrf
from tests._helpers import login_as


def _fake_request(*, method: str, cookie_header: str | None) -> Request:
    headers = [(b"host", b"testserver")]
    if cookie_header is not None:
        headers.append((b"cookie", cookie_header.encode()))
    scope = {
        "type": "http",
        "method": method,
        "path": "/api/v1/items",
        "headers": headers,
    }
    return Request(scope)


async def test_require_csrf_noop_for_safe_methods():
    request = _fake_request(method="GET", cookie_header=None)
    await require_csrf(request, x_csrf_token=None)  # must not raise


async def test_require_csrf_rejects_missing_cookie_and_header():
    request = _fake_request(method="POST", cookie_header=None)
    try:
        await require_csrf(request, x_csrf_token=None)
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["code"] == "CSRF_INVALID"
    else:
        raise AssertionError("expected HTTPException")


async def test_require_csrf_rejects_mismatched_header():
    request = _fake_request(method="POST", cookie_header="csrf_token=abc123")
    try:
        await require_csrf(request, x_csrf_token="not-the-same-value")
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["code"] == "CSRF_INVALID"
    else:
        raise AssertionError("expected HTTPException")


async def test_require_csrf_accepts_matching_cookie_and_header():
    request = _fake_request(method="POST", cookie_header="csrf_token=abc123")
    await require_csrf(request, x_csrf_token="abc123")  # must not raise


async def test_post_items_rejected_without_csrf_header(client, db_session):
    """Integration-level check on a real write endpoint: a request with a
    valid session but a wrong/absent CSRF header is rejected with 403,
    *before* it reaches the RBAC/business logic (a counter user, who would
    otherwise be allowed to create an item, still gets 403 CSRF_INVALID)."""
    await login_as(client, db_session, role=UserRole.counter)

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "王小明"},
        headers={"X-CSRF-Token": "definitely-wrong"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_INVALID"


async def test_post_items_accepted_with_valid_csrf_header(client, db_session):
    """Sanity check for the flip side, using the real cookie value directly
    (rather than relying on the test client's auto-attach hook) so this test
    demonstrates the actual double-submit contract end-to-end."""
    await login_as(client, db_session, role=UserRole.counter)

    token = client.cookies.get("csrf_token")
    assert token, "expected a csrf_token cookie to be set after login"

    resp = await client.post(
        "/api/v1/items",
        json={"recipient_name_raw": "王小明"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 201
