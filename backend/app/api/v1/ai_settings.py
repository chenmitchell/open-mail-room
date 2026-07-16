"""Admin AI status/model-list/settings endpoints (M9-BE task brief):
`GET /admin/ai/status`, `GET /admin/ai/models`, `PUT /admin/ai/settings`.

Complements `app/api/v1/ai_providers.py` (the DB-managed `ai_provider_configs`
CRUD): this router is about the *host-env-var* AI key path
(`AI_API_KEY`/`GEMINI_API_KEY`/`GOOGLE_API_KEY` -- app/config.py) that
`app/ocr/pipeline.py` falls back to when there is no active DB provider row --
"讓 OCR 用主機環境變數的 AI key 運作、模型自動抓、加每日請求上限防濫用,並提供
AI 狀態/模型清單/設定端點". Admin-only, same trust tier as the rest of
`/admin/*`; GET endpoints are safe methods so `require_csrf` (mounted
router-wide, matching every other admin sub-router) is a no-op for them and
only actually gates the `PUT`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.config import get_settings
from app.db import get_session
from app.models.ai_provider_config import AiProviderConfig
from app.models.enums import UserRole
from app.models.user import User
from app.notify.settings_store import get_setting, set_setting
from app.ocr.pipeline import (
    AI_DAILY_LIMIT_SETTING_KEY,
    AI_MODEL_SETTING_KEY,
    count_ocr_jobs_today,
    effective_daily_request_limit,
)
from app.ocr.providers import list_google_models
from app.security.csrf import require_csrf
from app.security.rbac import require_role
from app.services.audit import record_audit

router = APIRouter(prefix="/admin/ai", tags=["ai_settings"], dependencies=[Depends(require_csrf)])

ADMIN_ONLY = (UserRole.admin,)

MIN_DAILY_LIMIT = 1
MAX_DAILY_LIMIT = 100000


async def _has_active_db_config(session: AsyncSession) -> bool:
    stmt = select(AiProviderConfig.id).where(AiProviderConfig.is_active.is_(True)).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _status_payload(session: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    model_override = await get_setting(session, AI_MODEL_SETTING_KEY, default=None)
    effective_model = model_override or settings.ai_model or ""
    daily_limit = await effective_daily_request_limit(session)
    used_today = await count_ocr_jobs_today(session)
    has_db_config = await _has_active_db_config(session)
    return {
        "env_key_present": bool(settings.ai_api_key),
        "provider": settings.ai_provider,
        "effective_model": effective_model,
        "daily_request_limit": daily_limit,
        "used_today": used_today,
        "has_db_config": has_db_config,
    }


class AiSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, max_length=128)
    daily_request_limit: int | None = Field(default=None, ge=MIN_DAILY_LIMIT, le=MAX_DAILY_LIMIT)


def _no_key_error() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "AI_NO_KEY",
            "message": (
                "No AI_API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY environment variable "
                "is configured on this host"
            ),
        },
    )


def _models_unavailable_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "AI_MODELS_UNAVAILABLE", "message": message},
    )


@router.get("/status")
async def get_ai_status(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*ADMIN_ONLY)),
):
    return ok(await _status_payload(session))


@router.get("/models")
async def get_ai_models(
    _user: User = Depends(require_role(*ADMIN_ONLY)),
):
    settings = get_settings()
    if not settings.ai_api_key:
        raise _no_key_error()
    try:
        models = await list_google_models(settings.ai_api_key)
    except Exception as exc:  # noqa: BLE001 - any ListModels failure -> 400 for the admin UI
        raise _models_unavailable_error(str(exc)) from exc
    return ok({"models": models})


@router.put("/settings")
async def update_ai_settings(
    payload: AiSettingsUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*ADMIN_ONLY)),
):
    before = await _status_payload(session)
    updates = payload.model_dump(exclude_unset=True)

    if "model" in updates:
        model_value = (updates["model"] or "").strip()
        await set_setting(session, AI_MODEL_SETTING_KEY, model_value or None)

    if "daily_request_limit" in updates and updates["daily_request_limit"] is not None:
        await set_setting(
            session, AI_DAILY_LIMIT_SETTING_KEY, int(updates["daily_request_limit"])
        )

    after = await _status_payload(session)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="ai_settings.update",
        target_type="ai_settings",
        target_id="env",
        diff={"before": before, "after": after},
    )
    await session.commit()
    return ok(after)
