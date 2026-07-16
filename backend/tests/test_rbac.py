import pytest
from fastapi import HTTPException

from app.models.enums import UserRole
from app.models.user import User
from app.security.rbac import require_role


def _fake_user(role: UserRole) -> User:
    return User(
        id="fake-id",
        email="fake@example.com",
        password_hash="not-a-real-hash",
        display_name="Fake User",
        role=role,
        is_active=True,
    )


async def test_rbac_deny():
    """A viewer must be rejected by an admin-only dependency (403 FORBIDDEN)."""
    dependency = require_role(UserRole.admin)
    viewer = _fake_user(UserRole.viewer)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(user=viewer)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "FORBIDDEN"


async def test_rbac_allow():
    """An admin must pass through an admin-only dependency unchanged."""
    dependency = require_role(UserRole.admin)
    admin = _fake_user(UserRole.admin)

    result = await dependency(user=admin)

    assert result is admin


async def test_rbac_allow_multiple_roles():
    dependency = require_role(UserRole.admin, UserRole.counter)
    counter_user = _fake_user(UserRole.counter)

    result = await dependency(user=counter_user)

    assert result is counter_user
