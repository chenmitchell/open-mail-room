"""Background OCR job runner.

Kicked off via `asyncio.create_task(run_ocr_job(...))` from
`POST /ocr/jobs` (app/api/v1/ocr_jobs.py) -- mirrors the fire-and-forget
in-process background-work shape already used for notification queueing
(app/services/notify.py enqueues rows; nothing in this milestone's scope
runs a separate worker process, so this task runs inline in the API
process, same as the rest of the app).

Failover + retry (04-AI-OCR.md section 2 / section 4, and the task brief):
for each *active* `ai_provider_configs` row in ascending `priority` order,
try up to `MAX_ATTEMPTS_PER_PROVIDER` times with exponential backoff; on
persistent failure move to the next provider; if every provider is
exhausted the job is dead-lettered (`status=failed`) -- "全掛則 job 標
failed,櫃台仍可手動填寫". A provider's cumulative cost for the current
calendar month is checked after every successful call; crossing
`monthly_budget_usd` disables that provider (`is_active=False`) and writes
an audit log entry, per 04 section 4 / the task brief.

Testing note: this background task opens its *own* `AsyncSession` (via
`get_sessionmaker()`) that is live concurrently with whatever session a
polling `GET /ocr/jobs/{id}` request is using. Under the test suite's
`sqlite+aiosqlite:///:memory:` + `StaticPool` setup (tests/conftest.py --
in-memory SQLite is per-connection, so the whole engine is pinned to a
single shared DBAPI connection), two sessions genuinely overlapping in time
on that one connection can wedge indefinitely instead of erroring or simply
serializing -- confirmed by an end-to-end smoke test where the job sat in
`running` forever until the polling loop stopped, but completed in well
under a second against a real file-backed SQLite DB or when awaited
directly with no concurrent session. This is a `:memory:`+`StaticPool`-only
artifact, not a bug in this pipeline or a concern for real deployments
(file SQLite / PostgreSQL both hand out independent connections) --
`tests/_helpers.py`'s `drain_background_ocr_tasks()` works around it by
awaiting the background task to completion *before* the test's next request
opens a new session, so no two sessions are ever concurrently in flight.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_sessionmaker
from app.models.ai_provider_config import AiProviderConfig
from app.models.attachment import Attachment
from app.models.enums import ActorType, AiProvider, MailType, OcrStatus
from app.models.ocr_job import OcrJob
from app.notify.settings_store import get_int_setting, get_setting
from app.ocr.image_prep import prepare_for_ai
from app.ocr.postprocess import cross_validate_tracking
from app.ocr.prompts import PROMPT_VERSION, build_prompt
from app.ocr.providers import (
    ProviderError,
    build_provider,
    default_model_for,
    estimate_cost_usd,
    resolve_google_model,
)
from app.ocr.schema import clean_tracking_no
from app.security.file_crypto import read_encrypted_file
from app.services.audit import record_audit

logger = logging.getLogger(__name__)

MAX_ATTEMPTS_PER_PROVIDER = 3
_BACKOFF_BASE_SECONDS = 0.05

# SPEED-1: process-wide cache of the auto-resolved Google model. Without this,
# an env-key deployment (cfg.model is None for Google) did a ListModels HTTP
# round-trip *before every single OCR vision call* -- pure added latency the
# counter feels on every photo. The model a key supports doesn't change
# minute-to-minute, so resolve it once and reuse for a few hours. Keyed by the
# api key so rotating the key re-resolves. TTL is short enough that a newly
# enabled model shows up the same day without a restart.
_google_model_cache: dict[str, tuple[str, float]] = {}
_GOOGLE_MODEL_CACHE_TTL_SECONDS = 6 * 60 * 60

# SPEED-3: substrings that mean "the AI key is being rate-limited / out of
# quota" rather than a genuine content/parse failure -- surfaced to the
# counter as an actionable message instead of a raw provider dump.
_RATE_LIMIT_MARKERS = ("429", "resource_exhausted", "rate limit", "quota")


async def _resolve_google_model_cached(api_key: str) -> str:
    """resolve_google_model() with a process-wide TTL cache (SPEED-1)."""
    key = api_key or ""
    now = time.monotonic()
    cached = _google_model_cache.get(key)
    if cached and now - cached[1] < _GOOGLE_MODEL_CACHE_TTL_SECONDS:
        return cached[0]
    model = await resolve_google_model(api_key)
    _google_model_cache[key] = (model, now)
    return model


def _friendly_provider_error(raw: str | None) -> str:
    """Turn a raw provider failure into a counter-facing message. Rate-limit
    / quota exhaustion (common on a free-tier key) gets a specific hint to
    switch to a billing-enabled key, since that's the actual fix."""
    if not raw:
        return "All configured AI providers failed"
    low = raw.lower()
    if any(marker in low for marker in _RATE_LIMIT_MARKERS):
        return (
            "AI 金鑰已達速率/配額上限(免費層限流)。"
            "請改用已綁定帳單的付費金鑰,或稍後再試。"
            f"(原始錯誤:{raw})"
        )
    return raw

# M9-BE: settings-table keys for the admin-overridable AI model / daily
# request cap (app/api/v1/ai_settings.py writes these; this module reads
# them back so an override takes effect on the very next OCR job, no
# restart needed).
AI_MODEL_SETTING_KEY = "ai.model"
AI_DAILY_LIMIT_SETTING_KEY = "ai.daily_request_limit"

# M9-BE: daily request cap is a per-*day-in-Taipei* count of ocr_jobs rows
# created since local midnight, not a UTC day -- the counter/admin persona
# this product is built for reasons about "today" in local wall-clock time
# (Asia/Taipei, per the task brief), so a UTC-midnight boundary would flip
# the counter over at 8am/9am local time and confuse anyone reading it.
_TAIPEI_TZ = timezone(timedelta(hours=8))  # 台灣固定 UTC+8,無 DST;不依賴系統 tzdata


def _backoff_seconds(attempt: int) -> float:
    return _BACKOFF_BASE_SECONDS * (2**attempt)


def _current_month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _active_provider_configs(session: AsyncSession) -> list[AiProviderConfig]:
    stmt = (
        select(AiProviderConfig)
        .where(AiProviderConfig.is_active.is_(True))
        .order_by(AiProviderConfig.priority.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


def _taipei_day_start_utc(now: datetime | None = None) -> datetime:
    """UTC instant corresponding to today's local midnight in Asia/Taipei."""
    now_taipei = (now or datetime.now(timezone.utc)).astimezone(_TAIPEI_TZ)
    start_taipei = now_taipei.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_taipei.astimezone(timezone.utc)


async def count_ocr_jobs_today(
    session: AsyncSession, *, exclude_job_id: str | None = None
) -> int:
    """Number of `ocr_jobs` rows created since local (Asia/Taipei) midnight.

    Counts every job creation attempt (regardless of eventual status), since
    the daily cap exists to bound *outbound calls to the host's AI key*, not
    just successes -- a flood of jobs that all fail over every provider
    still burns the same quota-limited key.

    `exclude_job_id`: `run_ocr_job` commits the `OcrJob` row (status=queued)
    *before* its background task -- the one that runs this check -- ever
    starts, so by the time the cap is checked the job being processed has
    already counted itself. Passing its own id here keeps "N jobs created
    today" meaning "N jobs before this one", so a limit of N lets exactly N
    jobs through and blocks starting at the (N+1)th, rather than the
    (N)th.
    """
    day_start = _taipei_day_start_utc()
    stmt = select(func.count()).select_from(OcrJob).where(OcrJob.created_at >= day_start)
    if exclude_job_id is not None:
        stmt = stmt.where(OcrJob.id != exclude_job_id)
    return (await session.execute(stmt)).scalar_one()


async def effective_daily_request_limit(session: AsyncSession) -> int:
    """Admin override (`settings` table key `ai.daily_request_limit`) if
    present, else the `AI_DAILY_REQUEST_LIMIT` env var / default (10000)."""
    settings = get_settings()
    return await get_int_setting(
        session, AI_DAILY_LIMIT_SETTING_KEY, default=settings.ai_daily_request_limit
    )


async def _env_fallback_provider_configs(session: AsyncSession) -> list[SimpleNamespace] | None:
    """Build a single duck-typed "provider config" from host env vars
    (AI_API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY, etc. -- app/config.py)
    when there is no active `ai_provider_configs` DB row. Returns None when
    no env API key is configured either, so the caller can fall back to the
    "no provider at all" error.

    This mirrors the shape of an `AiProviderConfig` row closely enough that
    the rest of `run_ocr_job`'s loop (build_provider/_check_budget/etc.)
    doesn't need to know the difference: `id="env"` (so `OcrJob.provider`
    still gets a non-null, human-legible value), `monthly_budget_usd=None`
    (so `_check_budget` no-ops -- budget enforcement only applies to
    DB-managed providers), `priority=0` (irrelevant, this is always the only
    entry in the list).
    """
    settings = get_settings()
    if not settings.ai_api_key:
        return None

    try:
        provider_enum = AiProvider(settings.ai_provider or "google")
    except ValueError:
        provider_enum = AiProvider.google

    model_override = await get_setting(session, AI_MODEL_SETTING_KEY, default=None)
    model = model_override or settings.ai_model or None

    env_cfg = SimpleNamespace(
        id="env",
        provider=provider_enum,
        base_url=(settings.ai_base_url or None),
        api_key_encrypted=settings.ai_api_key,
        model=model,
        monthly_budget_usd=None,
        is_active=True,
        priority=0,
    )
    return [env_cfg]


async def _check_budget(session: AsyncSession, cfg: AiProviderConfig) -> None:
    if cfg.monthly_budget_usd is None:
        return
    month_start = _current_month_start()
    stmt = select(func.coalesce(func.sum(OcrJob.cost_estimate), 0.0)).where(
        OcrJob.provider == cfg.id,
        OcrJob.created_at >= month_start,
        OcrJob.cost_estimate.is_not(None),
    )
    spent = (await session.execute(stmt)).scalar_one()
    if spent >= cfg.monthly_budget_usd and cfg.is_active:
        cfg.is_active = False
        await record_audit(
            session,
            request=None,
            actor=None,
            actor_type=ActorType.system,
            action="ai_provider.budget_exceeded",
            target_type="ai_provider_config",
            target_id=cfg.id,
            diff={"monthly_budget_usd": cfg.monthly_budget_usd, "spent_usd": spent},
        )
        await session.flush()


def _barcode_tracking_no(barcode_results: dict | None) -> str | None:
    """M2-R1 contract gap #4: "條碼優先只在前端記憶體有效" -- previously the
    barcode-scanned value only ever won in the *frontend's* pre-fill logic
    (ocrConfirmForm.ts's resolveTrackingNo), so a page refresh or an
    offline-queue resubmit (which re-creates the job server-side with no
    client state left) lost it entirely and silently fell back to the AI's
    guess. Promoting the barcode value into `result_json.tracking_no` here
    makes "barcode wins" a server-side fact of the job's stored result, not
    something that only holds as long as the original browser tab/session is
    still around. Picks the first non-empty value (deterministic: dict
    insertion order, i.e. the order `barcode_hints` was submitted in) --
    barcode reads are exact, so which *specific* attachment they came from
    doesn't matter once there's a single unambiguous value.
    """
    if not barcode_results:
        return None
    for value in barcode_results.values():
        cleaned = clean_tracking_no(value)
        if cleaned:
            return cleaned
    return None


async def sweep_orphan_ocr_jobs(session: AsyncSession) -> int:
    """M2-R1 suggestion (adopted): a process restart/crash while a job was
    `running` (or `queued` but its background task never actually got
    launched, e.g. a crash between the `commit()` and `create_task()` in
    `POST /ocr/jobs`) leaves that job stuck forever -- nothing will ever move
    it out of `running`/`queued` again, since the in-memory background task
    that owned it is gone. Called once at app startup (see app/main.py);
    marks every such orphan `failed` with a clear, distinguishable error so
    the counter can just retry (re-run OCR) rather than "requeue and
    silently re-run", which could double-bill a provider for a call that may
    have actually completed server-side before the crash but never got
    written back. Returns the number of jobs swept, for startup logging.
    """
    stmt = select(OcrJob).where(OcrJob.status.in_((OcrStatus.queued, OcrStatus.running)))
    orphans = (await session.execute(stmt)).scalars().all()
    for job in orphans:
        job.status = OcrStatus.failed
        job.error = "Interrupted by a server restart; please retry OCR for this item."
    if orphans:
        await session.commit()
    return len(orphans)


def _decrypt_and_prepare(file_paths: list[str]) -> list[bytes]:
    """Sync, CPU-bound: decrypt each stored original and shrink it for the AI
    call. Runs off the event loop (see _load_ai_images) -- Pillow's LANCZOS
    resize and the AES decrypt are blocking work that, done inline in the
    async pipeline, froze the very same event loop that answers the confirm
    page's `GET /ocr/jobs/{id}` polling on a 1-CPU box, making OCR look
    "stuck" (SPEED-2)."""
    out: list[bytes] = []
    for path in file_paths:
        plaintext = read_encrypted_file(path)
        out.append(prepare_for_ai(plaintext))
    return out


async def _load_ai_images(session: AsyncSession, attachment_ids: list[str]) -> list[bytes]:
    # DB reads stay on the event loop (async session); only the blocking
    # decrypt+resize is offloaded to a worker thread.
    file_paths: list[str] = []
    for attachment_id in attachment_ids:
        attachment = await session.get(Attachment, attachment_id)
        if attachment is None:
            continue
        file_paths.append(attachment.file_path)
    if not file_paths:
        return []
    return await asyncio.to_thread(_decrypt_and_prepare, file_paths)


async def _fail_job(session: AsyncSession, job: OcrJob, *, error: str, retries: int) -> None:
    job.status = OcrStatus.failed
    job.error = error[:2000]
    job.retries = retries
    await session.commit()


async def run_ocr_job(job_id: str, *, mail_type: MailType | None = None) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            job = await session.get(OcrJob, job_id)
            if job is None or job.status != OcrStatus.queued:
                return

            job.status = OcrStatus.running
            await session.commit()

            try:
                images = await _load_ai_images(session, job.attachment_ids)
            except Exception as exc:  # noqa: BLE001
                logger.exception("ocr_job %s: failed to load/prepare images", job_id)
                await _fail_job(session, job, error=f"image preparation failed: {exc}", retries=0)
                return

            if not images:
                await _fail_job(
                    session, job, error="No readable attachments for this job", retries=0
                )
                return

            barcode_known = bool(job.barcode_results)
            prompt = build_prompt(mail_type=mail_type, barcode_known=barcode_known)

            configs = await _active_provider_configs(session)
            if not configs:
                configs = await _env_fallback_provider_configs(session)
            if not configs:
                await _fail_job(
                    session,
                    job,
                    error=(
                        "No active AI provider is configured. "
                        "請設定 AI_API_KEY / GEMINI_API_KEY 環境變數,或在 AI 設定新增供應商"
                    ),
                    retries=0,
                )
                return

            daily_limit = await effective_daily_request_limit(session)
            used_today = await count_ocr_jobs_today(session, exclude_job_id=job.id)
            if used_today >= daily_limit:
                await _fail_job(
                    session,
                    job,
                    error=f"已達每日 AI 請求上限({daily_limit} 次/日),請明日再試或調高上限",
                    retries=0,
                )
                return

            last_error: str | None = None
            total_attempts = 0

            for cfg in configs:
                try:
                    provider = build_provider(
                        cfg.provider, base_url=cfg.base_url, api_key=cfg.api_key_encrypted
                    )
                except ProviderError as exc:
                    last_error = str(exc)
                    continue

                model = cfg.model or default_model_for(cfg.provider)
                if cfg.provider == AiProvider.google and not cfg.model:
                    # Discovery is best-effort AND cached (SPEED-1): keep the
                    # DEFAULT_MODELS fallback already assigned above if the
                    # (once-per-6h) ListModels lookup errors out.
                    with contextlib.suppress(Exception):
                        model = await _resolve_google_model_cached(cfg.api_key_encrypted)
                if not model:
                    last_error = f"{cfg.provider.value}: no model configured"
                    continue

                result = None
                for attempt in range(MAX_ATTEMPTS_PER_PROVIDER):
                    total_attempts += 1
                    try:
                        result = await provider.extract(images, prompt=prompt, model=model)
                        break
                    except Exception as exc:  # noqa: BLE001 - any provider failure -> retry/failover
                        last_error = f"{cfg.provider.value}: {exc}"
                        logger.warning(
                            "ocr_job %s: provider %s attempt %d/%d failed: %s",
                            job_id,
                            cfg.provider.value,
                            attempt + 1,
                            MAX_ATTEMPTS_PER_PROVIDER,
                            exc,
                        )
                        if attempt < MAX_ATTEMPTS_PER_PROVIDER - 1:
                            await asyncio.sleep(_backoff_seconds(attempt))

                if result is None:
                    continue  # exhausted this provider, fail over to the next one

                # Barcode-scanned tracking numbers win over the AI's guess
                # (04-AI-OCR.md section 1 "條碼優先,AI 補位"), and now do so
                # in the persisted result, not just the frontend's transient
                # pre-fill -- see _barcode_tracking_no's docstring. Applied
                # *before* cross-validation so carrier-pattern matching
                # reasons about the tracking number that actually ends up in
                # result_json / the draft, not the (possibly overridden) AI
                # guess.
                barcode_tracking_no = _barcode_tracking_no(job.barcode_results)
                final_tracking_no = barcode_tracking_no or result.tracking_no
                if barcode_tracking_no:
                    result = replace(result, tracking_no=barcode_tracking_no)

                validation = await cross_validate_tracking(session, result)
                cost_estimate = estimate_cost_usd(cfg.provider, result.tokens_in, result.tokens_out)

                job.provider = cfg.id
                job.model = model
                job.status = OcrStatus.succeeded
                job.prompt_version = PROMPT_VERSION
                job.confidence = validation["confidence"]
                job.tokens_in = result.tokens_in
                job.tokens_out = result.tokens_out
                job.cost_estimate = cost_estimate
                job.retries = total_attempts - 1
                job.error = None
                job.result_json = {
                    "tracking_no": final_tracking_no,
                    "carrier_guess": result.carrier_guess,
                    "carrier_id": validation["carrier_id"],
                    "sender_name": result.sender_name,
                    "sender_org": result.sender_org,
                    "sender_phone": result.sender_phone,
                    "recipient_name": result.recipient_name,
                    "recipient_dept_hint": result.recipient_dept_hint,
                    "is_handwritten": result.is_handwritten,
                    "warnings": validation["warnings"],
                }
                await session.flush()
                await _check_budget(session, cfg)
                await session.commit()
                return

            await _fail_job(
                session,
                job,
                error=_friendly_provider_error(last_error),
                retries=total_attempts,
            )
        except Exception as exc:  # noqa: BLE001 - top-level safety net, never crash the event loop
            logger.exception("ocr_job %s: unhandled error in background pipeline", job_id)
            await session.rollback()
            try:
                job = await session.get(OcrJob, job_id)
                if job is not None:
                    job.status = OcrStatus.failed
                    job.error = f"internal error: {exc}"[:2000]
                    await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception("ocr_job %s: failed to record failure state", job_id)
