from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.envelope import fail
from app.api.v1 import api_v1_router
from app.config import get_settings
from app.db import check_db_ready, get_sessionmaker
from app.models.types import validate_encryption_keys_or_raise
from app.notify.scheduler import run_daily_reminder_sweep
from app.notify.worker import sweep_orphan_notifications
from app.ocr.pipeline import sweep_orphan_ocr_jobs
from app.security.body_limit import BodySizeLimitMiddleware
from app.security.upload_limits import MAX_UPLOAD_BATCH_BYTES
from app.services.retention import run_retention_sweep

logger = logging.getLogger(__name__)

# RC-FIX #6: neither the reminder/unclaimed sweep
# (app.notify.scheduler.run_daily_reminder_sweep) nor the retention sweep
# (app.services.retention.run_retention_sweep) was ever wired to run
# automatically -- both existed only as plain async functions invoked
# directly by tests (see their module docstrings: "Not wired to a cron by
# this milestone"). This app is single-process with no separate
# scheduler/cron, so both are driven by one in-process asyncio background
# loop started at app startup: first run 60s after startup (let the app
# finish booting first), then every 24h. Real (non-dry-run) sweeps.
DAILY_SWEEP_INITIAL_DELAY_SECONDS = 60
DAILY_SWEEP_INTERVAL_SECONDS = 24 * 60 * 60

# ZEABUR-1: paths the SPA catch-all must never intercept, even though it's a
# broad `/{full_path:path}` GET route. Under normal routing this doesn't
# actually matter -- Starlette tries routes in registration order and the
# API router / /healthz / /readyz are all registered before the catch-all,
# so an exact match always wins first. It DOES matter for an *unmatched*
# API path like `GET /api/v1/does-not-exist`: FastAPI's router.APIRoute
# lookups for `/api/v1/*` all fail to match that path, so routing falls
# through to whatever route matches next -- which, without this guard, would
# be the SPA catch-all happily returning `index.html` with a 200 instead of
# the JSON 404 envelope API clients expect.
_SPA_EXCLUDED_PREFIXES = ("api/", "healthz", "readyz")


def _is_spa_excluded_path(full_path: str) -> bool:
    return full_path == "api" or full_path.startswith(_SPA_EXCLUDED_PREFIXES)


async def run_daily_sweeps_once(session_factory: async_sessionmaker) -> None:
    """Runs the reminder/unclaimed sweep and the retention sweep exactly
    once each, one DB session per sweep. Each sweep is independently
    try/except-wrapped so a failure in one (or in a single iteration) never
    takes down the other sweep or the background loop itself -- same
    "never block/crash the app" policy as the orphan-job sweeps below.
    Factored out from the loop so it can be exercised directly by tests
    without waiting on `asyncio.sleep`.
    """
    try:
        async with session_factory() as session:
            stats = await run_daily_reminder_sweep(session)
        logger.info("daily sweep: reminder/unclaimed sweep done: %s", stats)
    except Exception:  # noqa: BLE001
        logger.exception("daily sweep: reminder/unclaimed sweep failed")

    try:
        async with session_factory() as session:
            stats = await run_retention_sweep(session, dry_run=False)
        logger.info("daily sweep: retention sweep done: %s", stats)
    except Exception:  # noqa: BLE001
        logger.exception("daily sweep: retention sweep failed")


async def _daily_sweep_loop() -> None:
    await asyncio.sleep(DAILY_SWEEP_INITIAL_DELAY_SECONDS)
    while True:
        await run_daily_sweeps_once(get_sessionmaker())
        await asyncio.sleep(DAILY_SWEEP_INTERVAL_SECONDS)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'",
    "X-Frame-Options": "DENY",
}


class SecurityHeadersMiddleware:
    """Adds baseline security headers to every response.

    HSTS is only meaningful (and only added) over HTTPS -- browsers ignore it
    on plain HTTP, and it would be actively wrong to send it while e.g.
    running behind a dev server on http://localhost.

    Implemented as a plain ASGI middleware, *not*
    `starlette.middleware.base.BaseHTTPMiddleware` (M2-01): BaseHTTPMiddleware
    runs the downstream app in a separate anyio-managed task per request,
    which is a documented source of surprising interactions with
    fire-and-forget `asyncio.create_task(...)` background work started from
    inside a request it wraps (encode/starlette#1438) -- e.g. the OCR
    background job launched by `POST /ocr/jobs` (app/api/v1/ocr_jobs.py).
    `BodySizeLimitMiddleware` already avoided `BaseHTTPMiddleware` for a
    related reason (see its own docstring); this class is written the same
    way as a precaution. (The actual hang chased down while building the OCR
    background-job pipeline turned out to be a *different*, SQLite-specific
    issue -- see app/ocr/pipeline.py's module docstring and
    tests/_helpers.py's `drain_background_ocr_tasks` -- but avoiding
    BaseHTTPMiddleware here remains good practice regardless.)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_https = scope.get("scheme") == "https"

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers: list[tuple[bytes, bytes]] = message.setdefault("headers", [])
                existing = {name.decode("latin-1").lower() for name, _ in raw_headers}
                for header, value in SECURITY_HEADERS.items():
                    if header.lower() not in existing:
                        raw_headers.append((header.encode("latin-1"), value.encode("latin-1")))
                if is_https and "strict-transport-security" not in existing:
                    raw_headers.append(
                        (
                            b"Strict-Transport-Security",
                            b"max-age=31536000; includeSubDomains",
                        )
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        body = fail(str(detail["code"]), str(detail["message"]))
    else:
        body = fail("HTTP_ERROR", str(detail))
    return JSONResponse(status_code=exc.status_code, content=body)


def _format_validation_errors(errors: list) -> str:
    """Human-readable one-liner instead of the raw pydantic errors() repr,
    which used to leak "[{'type': ..., 'loc': ('query', 'size'), ...}]"
    straight to the UI. Shows up to 3 "field: message" pairs, dropping the
    leading body/query/path location segment for readability."""
    parts: list[str] = []
    for err in errors[:3]:
        loc = [str(x) for x in err.get("loc", ()) if x not in ("body", "query", "path")]
        field = ".".join(loc)
        msg = str(err.get("msg", "invalid value"))
        parts.append(f"{field}: {msg}" if field else msg)
    return "；".join(parts) or "輸入驗證失敗"


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=fail("VALIDATION_ERROR", _format_validation_errors(exc.errors())),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak stack traces / internals to clients (07-SECURITY.md section 5).
    return JSONResponse(status_code=500, content=fail("INTERNAL_ERROR", "Internal server error"))


def _mount_spa(app: FastAPI, settings) -> None:
    """ZEABUR-1: optionally serve the built frontend from the same process.

    Zeabur runs this as a single container per service behind an ingress
    that terminates TLS and reverse-proxies to one HTTP port -- there's no
    separate static-file service the way the self-hosted docker-compose +
    Caddy path has one. So when SERVE_FRONTEND is enabled (the default),
    the backend itself serves the Vite build output (FRONTEND_DIST, default
    /app/frontend_dist) and falls back to index.html for any GET path that
    isn't a real static file and isn't one of the existing API/health
    routes -- standard SPA "history mode" client-side routing support.

    Deliberately never crashes app startup: a missing/incomplete dist dir
    (SERVE_FRONTEND=1 but nothing was built, e.g. the API-only
    docker-compose path, or a dev checkout without `npm run build`) just
    skips the mount with a log line, same fail-safe posture as
    app.config.load_branding.
    """
    if not settings.serve_frontend:
        logger.info("SERVE_FRONTEND disabled; not serving a static frontend from this process")
        return

    dist_dir = Path(settings.frontend_dist)
    index_file = dist_dir / "index.html"
    if not dist_dir.is_dir() or not index_file.is_file():
        logger.info(
            "SERVE_FRONTEND enabled but FRONTEND_DIST (%s) has no index.html; "
            "skipping static frontend mount",
            dist_dir,
        )
        return

    # Vite's default build output puts hashed JS/CSS bundles under
    # dist/assets/ -- mount that subtree via StaticFiles so they get proper
    # Content-Type/caching handling and a real 404 (not the SPA fallback) if
    # a stale/unknown bundle path is requested. Anything else under the dist
    # root (favicon.ico, manifest.webmanifest, robots.txt, ...) plus the SPA
    # fallback itself is handled by spa_fallback below.
    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if _is_spa_excluded_path(full_path):
            # Let a genuinely-unmatched /api/*, /healthz, /readyz path fall
            # through to FastAPI's normal 404 handling (JSON envelope via
            # _http_exception_handler) instead of returning index.html.
            raise HTTPException(
                status_code=404, detail={"code": "NOT_FOUND", "message": "Not Found"}
            )

        candidate = dist_dir / full_path if full_path else index_file
        if full_path and candidate.is_file():
            # Resolve and check the file is actually inside dist_dir before
            # serving it -- full_path comes straight from the URL, and
            # Starlette's `path` converter allows `/`-separated segments
            # (though not raw `..` traversal thanks to routing-level
            # normalization, this is cheap insurance against relying on
            # that alone).
            try:
                candidate.resolve().relative_to(dist_dir.resolve())
            except ValueError:
                raise HTTPException(
                    status_code=404, detail={"code": "NOT_FOUND", "message": "Not Found"}
                ) from None
            return FileResponse(candidate)

        return FileResponse(index_file)

    logger.info("Serving static frontend from %s (SPA fallback enabled)", dist_dir)


def create_app() -> FastAPI:
    settings = get_settings()

    # Fail fast on a misconfigured/weak encryption key rather than crashing
    # on the first encrypted write (M0-R1 blocking #5).
    validate_encryption_keys_or_raise()

    app = FastAPI(
        title="Open Mail Room API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(SecurityHeadersMiddleware)

    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    # else: no CORS middleware at all -> browsers enforce same-origin only,
    # which is the documented default (07-SECURITY.md section 5, "CORS defaults to same-origin").

    # Added last so it's outermost (Starlette wraps middleware in the
    # reverse of add-order, so the most-recently-added one runs first):
    # oversized/spoofed-length request bodies get rejected before any other
    # middleware or the router even sees them (M1-R1 blocking #1).
    app.add_middleware(
        BodySizeLimitMiddleware,
        path_overrides={"/api/v1/uploads": MAX_UPLOAD_BATCH_BYTES},
    )

    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    app.include_router(api_v1_router)

    @app.on_event("startup")
    async def _sweep_orphan_ocr_jobs_on_startup() -> None:
        # M2-R1 suggestion (adopted): a job stuck in queued/running from
        # before this process last stopped (crash, deploy restart, ...) has
        # no background task left to ever finish it -- fail it so the
        # counter can retry rather than see it stuck forever. Never allowed
        # to block/crash startup: a DB that isn't reachable/migrated yet is
        # already surfaced by /readyz, not this best-effort sweep.
        try:
            session_factory = get_sessionmaker()
            async with session_factory() as session:
                swept = await sweep_orphan_ocr_jobs(session)
            if swept:
                logger.warning("startup: swept %d orphaned OCR job(s) to failed", swept)
        except Exception:  # noqa: BLE001
            logger.exception("startup: orphan OCR job sweep failed (continuing startup anyway)")

    @app.on_event("startup")
    async def _sweep_orphan_notifications_on_startup() -> None:
        # M3-01: mirrors the OCR orphan sweep above -- a notification whose
        # background delivery task never got to finish (crash mid-attempt)
        # is left with a stale `locked_at`; clear it and give it a fresh
        # delivery attempt rather than leaving it stuck forever.
        try:
            session_factory = get_sessionmaker()
            async with session_factory() as session:
                swept = await sweep_orphan_notifications(session)
            if swept:
                logger.warning("startup: swept %d orphaned notification(s)", swept)
        except Exception:  # noqa: BLE001
            logger.exception(
                "startup: orphan notification sweep failed (continuing startup anyway)"
            )

    @app.on_event("startup")
    async def _start_daily_sweep_loop_on_startup() -> None:
        # Fire-and-forget background task; never allowed to block or crash
        # startup itself (same policy as the two sweeps above) -- if even
        # *scheduling* the loop somehow fails, log and keep booting rather
        # than taking the whole app down over a background chore.
        try:
            task = asyncio.create_task(_daily_sweep_loop())
            # Keep a strong reference on app.state: asyncio only holds a
            # weak reference to scheduled tasks, so an unreferenced task can
            # be garbage-collected mid-run (a well-known asyncio footgun).
            app.state.daily_sweep_task = task
        except Exception:  # noqa: BLE001
            logger.exception(
                "startup: failed to schedule daily sweep loop (continuing startup anyway)"
            )

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        db_ok = await check_db_ready()
        status_code = 200 if db_ok else 503
        body = {"status": "ok" if db_ok else "error", "db": db_ok}
        return JSONResponse(status_code=status_code, content=body)

    # Registered last: the SPA catch-all route must come after every API
    # route above so Starlette's in-order route matching always tries the
    # real routes first (see _is_spa_excluded_path's docstring for the one
    # case -- unmatched /api/* paths -- where registration order alone
    # isn't enough and an explicit guard is required too).
    _mount_spa(app, settings)

    return app


app = create_app()
