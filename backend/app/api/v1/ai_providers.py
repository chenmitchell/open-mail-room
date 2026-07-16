"""Admin AI-provider configuration (03-API-SPEC.md section 2 "管理":
`GET|POST /admin/ai-providers`; task brief extends this to include PATCH).

"key 加密存、回應遮罩 sk-***abc" -- the encrypted key is write-only: it can
be set on create/update but is never read back, only a masked preview is
returned. Admin-only (same trust tier as the rest of `/admin/*`).

`base_url` IS run through an SSRF/private-network guard (app/security/ssrf.py,
M2-R1 blocking #1): even though this endpoint is admin-only, a request-forging
`base_url` still lets a compromised/careless admin session turn the OCR
pipeline's outbound HTTP call (which carries the decrypted provider API key
as a Bearer token) into an SSRF proxy against internal services -- including
the cloud metadata endpoint `169.254.169.254`. 04-AI-OCR.md section 2/5's
documented "point `base_url` at a local Ollama instance" deployment mode (a
private-network address by definition) is preserved as an explicit opt-in:
`allow_private_network=true` on the config.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import ok
from app.db import get_session
from app.models.ai_provider_config import AiProviderConfig
from app.models.enums import AiProvider, UserRole
from app.models.user import User
from app.security.csrf import require_csrf
from app.security.rbac import require_role
from app.security.ssrf import UnsafeBaseUrlError, check_base_url_allowed
from app.services.audit import record_audit

router = APIRouter(
    prefix="/admin/ai-providers", tags=["ai_providers"], dependencies=[Depends(require_csrf)]
)

ADMIN_ONLY = (UserRole.admin,)


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 6:
        return "*" * len(key)
    return f"{key[:3]}***{key[-3:]}"


def _serialize(cfg: AiProviderConfig) -> dict[str, Any]:
    return {
        "id": cfg.id,
        "provider": cfg.provider.value,
        "base_url": cfg.base_url,
        "api_key_masked": _mask_key(cfg.api_key_encrypted),
        "model": cfg.model,
        "priority": cfg.priority,
        "monthly_budget_usd": cfg.monthly_budget_usd,
        "is_active": cfg.is_active,
        "allow_private_network": cfg.allow_private_network,
        "created_at": cfg.created_at.isoformat(),
        "updated_at": cfg.updated_at.isoformat(),
    }


class AiProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AiProvider
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str = Field(min_length=1, max_length=1024)
    model: str | None = Field(default=None, max_length=128)
    priority: int = 0
    monthly_budget_usd: float | None = None
    is_active: bool = True
    # M2-R1 blocking #1: opt-in escape hatch for the SSRF guard below --
    # default False (safe by default).
    allow_private_network: bool = False


class AiProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, min_length=1, max_length=1024)
    model: str | None = Field(default=None, max_length=128)
    priority: int | None = None
    monthly_budget_usd: float | None = None
    is_active: bool | None = None
    allow_private_network: bool | None = None


def _unsafe_base_url(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "AI_PROVIDER_UNSAFE_BASE_URL", "message": message},
    )


async def _get_or_404(session: AsyncSession, config_id: str) -> AiProviderConfig:
    cfg = await session.get(AiProviderConfig, config_id)
    if cfg is None:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "AI provider not found"}
        )
    return cfg


@router.get("")
async def list_ai_providers(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*ADMIN_ONLY)),
):
    rows = (
        (await session.execute(select(AiProviderConfig).order_by(AiProviderConfig.priority.asc())))
        .scalars()
        .all()
    )
    return ok([_serialize(cfg) for cfg in rows])


@router.get("/{config_id}")
async def get_ai_provider(
    config_id: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(*ADMIN_ONLY)),
):
    cfg = await _get_or_404(session, config_id)
    return ok(_serialize(cfg))


@router.post("", status_code=201)
async def create_ai_provider(
    payload: AiProviderCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*ADMIN_ONLY)),
):
    try:
        check_base_url_allowed(
            payload.base_url, allow_private_network=payload.allow_private_network
        )
    except UnsafeBaseUrlError as exc:
        raise _unsafe_base_url(str(exc)) from exc

    cfg = AiProviderConfig(
        provider=payload.provider,
        base_url=payload.base_url,
        api_key_encrypted=payload.api_key,
        model=payload.model,
        priority=payload.priority,
        monthly_budget_usd=payload.monthly_budget_usd,
        is_active=payload.is_active,
        allow_private_network=payload.allow_private_network,
    )
    session.add(cfg)
    await session.flush()

    await record_audit(
        session,
        request=request,
        actor=user,
        action="ai_provider.create",
        target_type="ai_provider_config",
        target_id=cfg.id,
        diff={"after": {**_serialize(cfg), "api_key_masked": _mask_key(payload.api_key)}},
    )
    await session.commit()
    await session.refresh(cfg)
    return ok(_serialize(cfg))


@router.patch("/{config_id}")
async def update_ai_provider(
    config_id: str,
    payload: AiProviderUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(*ADMIN_ONLY)),
):
    cfg = await _get_or_404(session, config_id)
    before = _serialize(cfg)

    updates = payload.model_dump(exclude_unset=True)
    api_key = updates.pop("api_key", None)
    for field, value in updates.items():
        setattr(cfg, field, value)
    if api_key:
        cfg.api_key_encrypted = api_key

    # Re-validate the *effective* base_url/allow_private_network pair after
    # applying this PATCH -- a request that only touches one of the two
    # fields must still be checked against the other's (possibly pre-existing)
    # value, not just the delta.
    try:
        check_base_url_allowed(cfg.base_url, allow_private_network=cfg.allow_private_network)
    except UnsafeBaseUrlError as exc:
        raise _unsafe_base_url(str(exc)) from exc

    await session.flush()
    after = _serialize(cfg)

    await record_audit(
        session,
        request=request,
        actor=user,
        action="ai_provider.update",
        target_type="ai_provider_config",
        target_id=cfg.id,
        diff={"before": before, "after": after},
    )
    await session.commit()
    await session.refresh(cfg)
    return ok(_serialize(cfg))
