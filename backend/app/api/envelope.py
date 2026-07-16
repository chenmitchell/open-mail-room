"""The `{"data": ..., "error": ...}` response envelope required by
docs/plan/03-API-SPEC.md for every /api/v1 endpoint.
"""

from __future__ import annotations

from typing import Any


def ok(data: Any = None) -> dict[str, Any]:
    return {"data": data, "error": None}


def fail(code: str, message: str) -> dict[str, Any]:
    return {"data": None, "error": {"code": code, "message": message}}


def paginated(data: Any, *, total: int, page: int, size: int) -> dict[str, Any]:
    """List-endpoint envelope: `{ data, error: null, meta: { total, page,
    size } }` per docs/plan/03-API-SPEC.md section 2."""
    return {"data": data, "error": None, "meta": {"total": total, "page": page, "size": size}}
