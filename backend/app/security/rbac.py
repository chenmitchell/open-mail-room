"""Session extraction + role-based access control dependencies.

Every protected endpoint must depend on `get_current_user` (or
`require_role(...)`) -- RBAC is enforced here, server-side, per
07-SECURITY.md §2 ("RBAC 在後端每個端點強制檢查,不能只靠前端隱藏按鈕").
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.enums import UserRole
from app.models.user import User
from app.security.jwt import SESSION_COOKIE_NAME, InvalidSessionToken, decode_session_token


def _auth_error(message: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=401, detail={"code": "AUTH_INVALID", "message": message}
    )


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise _auth_error("Missing session cookie")
    try:
        payload = decode_session_token(token)
    except InvalidSessionToken as exc:
        raise _auth_error("Invalid or expired session") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise _auth_error("Malformed session token")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _auth_error("User not found or inactive")
    return user


def require_role(*roles: UserRole) -> Callable:
    """Dependency factory: `Depends(require_role(UserRole.admin))`."""

    allowed = set(roles)

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Role '{user.role.value}' is not permitted for this action",
                },
            )
        return user

    return _dependency
