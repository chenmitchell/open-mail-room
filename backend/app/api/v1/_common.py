"""Shared pagination helpers for list endpoints (03-API-SPEC.md section 2:
"分頁用 ?page=&size=,回 meta: { total, page, size }")."""

from __future__ import annotations

from fastapi import Query

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def pagination_params(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> tuple[int, int]:
    return page, size


def envelope_meta(*, total: int, page: int, size: int) -> dict:
    return {"total": total, "page": page, "size": size}
