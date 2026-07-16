"""Application configuration.

Reads environment variables (optionally from a `.env` file) via
pydantic-settings, and loads the self-hostable branding override file
`config/branding.yaml` from the repo root. The branding file is optional --
if it is missing or malformed we fall back to built-in defaults and never
crash the app because of it.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BRANDING_PATH = REPO_ROOT / "config" / "branding.yaml"

# ZEABUR-1: sentinels used to detect "the user didn't explicitly set
# DATABASE_URL / UPLOAD_DIR" so we can resolve their *effective* default
# based on whether DATA_DIR (the persistent volume Zeabur mounts) is
# actually present, without ever overriding a value the deployer set on
# purpose. See Settings._resolve_data_dependent_defaults below.
_LOCAL_DATABASE_URL_DEFAULT = "sqlite+aiosqlite:///./openmailroom.db"
_LOCAL_UPLOAD_DIR_DEFAULT = str(BACKEND_ROOT / "uploads")
_DEFAULT_DATA_DIR = "/data"

DEFAULT_BRANDING: dict[str, Any] = {
    "company_name": "Open Mail Room",
    "logo_url": None,
    "primary_color": "#0B5FFF",
    "language": "zh-Hant",
    "pickup_location": "一樓收發室",
    "field_toggles": {
        "cod_amount": True,
        "refrigeration": True,
        "size_note": True,
    },
    "retention_years": 5,
    # 05-NOTIFICATIONS.md section 4 default templates -- {variable}
    # interpolation is done by app/notify/templates.py. Admin overrides live
    # in the `settings` table (key "notify.templates"); these are the
    # fallback when no override (or no matching key in the override dict) is
    # configured. `received_confidential` is used automatically instead of
    # `received` whenever the mail item is confidential (never includes
    # sender/content), per "機密件模板:不含寄件人與內容描述".
    "notification_templates": {
        "received": (
            "📦 您有 {mail_type} 到櫃台|寄件:{sender}|單號:{tracking_no}|"
            "請至 {pickup_location} 領取,出示取件碼 {pickup_code}"
        ),
        "received_confidential": (
            "📦 您有一件機密郵件已送達,請至 {pickup_location} 領取,"
            "出示取件碼 {pickup_code}"
        ),
        "reminder": "提醒:您的包裹已到 {days} 天,請儘速領取",
        "overdue": "您有一件包裹已逾期滯留 {days} 天,請盡速處理(收件人:{recipient_name})",
        "outbound_shipped": "您申請的交寄件已寄出,託運單號:{tracking_no}",
    },
}


def _data_dir_usable(data_dir: str) -> bool:
    """True only if `data_dir` already exists and is writable.

    Deliberately does NOT try to create the directory here: this is called
    on every Settings() instantiation (including in tests, and in any local
    dev environment without a `/data` volume), and a `/data` mkdir side
    effect on a machine that happens to allow creating a top-level directory
    would be a surprising, hard-to-diagnose action-at-a-distance bug. Actual
    directory creation happens later, at the point of use (entrypoint.sh for
    secrets.env, app.security.file_crypto for uploads, the DB driver for the
    sqlite file's parent dir) -- never as a side effect of reading config.
    """
    try:
        path = Path(data_dir)
        return path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False


class Settings(BaseSettings):
    """Environment-driven settings. Instantiate via get_settings()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ZEABUR-1: persistent volume Zeabur mounts the container at. SQLite DB
    # file and uploaded attachments default to living under here so they
    # survive redeploys/restarts. Falls back to local, repo-relative paths
    # (the pre-existing defaults) when /data doesn't exist -- e.g. running
    # tests, `uvicorn app.main:app` straight from a dev checkout, or the
    # docker-compose self-hosted path, none of which mount anything at
    # /data. See _resolve_data_dependent_defaults.
    data_dir: str = Field(default=_DEFAULT_DATA_DIR, alias="DATA_DIR")

    # Port uvicorn should listen on. Not read directly by this module (the
    # process is actually started by scripts/entrypoint.sh, which reads
    # $PORT itself for the `uvicorn --port` flag) -- kept here too so the
    # rest of the app/tests has one canonical place to look up "what port
    # are we on" if ever needed, and so it's validated/typed like every
    # other setting instead of being a shell-only convention.
    port: int = Field(default=8080, alias="PORT")

    database_url: str = Field(
        default=_LOCAL_DATABASE_URL_DEFAULT,
        alias="DATABASE_URL",
    )
    secret_key: str = Field(default="", alias="SECRET_KEY")

    # Legacy single-key form (still honored, treated as key version "v1").
    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")

    # Multi-key form: JSON dict of {"k1": "<base64 32-byte key>", ...} plus
    # the version that should be used for *new* encryptions. Enables key
    # rotation without breaking decryption of data written under an older
    # key (M0-R1 blocking #4 / 07-SECURITY.md section 3, key rotation).
    encryption_keys: str = Field(default="", alias="ENCRYPTION_KEYS")
    encryption_active_key: str = Field(default="", alias="ENCRYPTION_ACTIVE_KEY")

    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    login_max_attempts: int = Field(default=5, alias="LOGIN_MAX_ATTEMPTS")
    login_lockout_minutes: int = Field(default=15, alias="LOGIN_LOCKOUT_MINUTES")

    cors_allow_origins: list[str] = Field(default_factory=list, alias="CORS_ALLOW_ORIGINS")

    branding_path: str = Field(default=str(DEFAULT_BRANDING_PATH), alias="BRANDING_PATH")

    # Directory encrypted attachments (pickup signatures, photos) are written
    # to. AES-256-GCM encrypted at rest via app.security.file_crypto, using
    # the same key registry as the DB-column `Encrypted` type (07-SECURITY.md
    # section 3 / section 4). Defaults to ${DATA_DIR}/uploads when DATA_DIR
    # is usable (ZEABUR-1), else the pre-existing backend-relative default.
    upload_dir: str = Field(default=_LOCAL_UPLOAD_DIR_DEFAULT, alias="UPLOAD_DIR")

    # Fail-safe default: an operator who forgets to set ENVIRONMENT=production
    # in their deployment ends up in the *safer* state (Secure cookies, no
    # dev-only key fallback), not the weaker "development" defaults
    # (M0-R1 blocking #2 / #5). Tests explicitly set ENVIRONMENT=development.
    environment: str = Field(default="production", alias="ENVIRONMENT")

    # SETUP-WIZARD: scripts/seed.py's admin auto-creation is strictly
    # opt-in now -- it only ever creates an admin when *both* of these are
    # explicitly set (e.g. CI/automated test environments), so both default
    # to blank rather than a real-looking placeholder ("admin@example.com"
    # previously defaulted here, which made an opt-in check impossible to
    # express: a value that's always present isn't optional). The normal
    # first-run path for humans is the `/api/v1/setup` wizard
    # (app/api/v1/setup.py) -- see scripts/seed.py's module docstring.
    # Still routed through Settings (not raw `os.environ`) so `.env` is
    # honored like every other setting (RC-FIX #8's original point,
    # unaffected by this change).
    admin_email: str = Field(default="", alias="ADMIN_EMAIL")
    admin_password: str = Field(default="", alias="ADMIN_PASSWORD")

    # ZEABUR-1: single-container deployment where the backend also serves
    # the built frontend (Zeabur's ingress terminates TLS in front of one
    # container per service, not a separate static-file service). Default
    # on; set SERVE_FRONTEND=0 to disable (e.g. running the API alone behind
    # the docker-compose+Caddy self-hosted path, where Caddy already serves
    # the frontend -- see deploy/docker-compose.yml).
    serve_frontend: bool = Field(default=True, alias="SERVE_FRONTEND")
    frontend_dist: str = Field(default="/app/frontend_dist", alias="FRONTEND_DIST")

    # --- AI OCR provider via host env vars (BYOK, no DB row / no web form) ---
    # When there is NO active ai_provider_configs DB row, the OCR pipeline
    # falls back to a provider built from these. Set at least an API key
    # (AI_API_KEY, or the common GEMINI_API_KEY / GOOGLE_API_KEY aliases).
    # AI_MODEL is optional -- if blank, the pipeline auto-discovers a
    # vision-capable model that the key actually supports (Google ListModels).
    ai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("AI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    ai_provider: str = Field(default="google", alias="AI_PROVIDER")
    ai_model: str = Field(default="", alias="AI_MODEL")
    ai_base_url: str = Field(default="", alias="AI_BASE_URL")

    # M9-BE: per-day cap on ocr_jobs creation, to bound abuse of the
    # host-env AI key (there is no per-request billing gate like the
    # DB-managed providers' monthly_budget_usd when running off the env-var
    # fallback). Admin can override at runtime via the `settings` table key
    # `ai.daily_request_limit` (PUT /admin/ai/settings) without redeploying.
    ai_daily_request_limit: int = Field(default=10000, alias="AI_DAILY_REQUEST_LIMIT")

    # M10: outbound SMTP for *system* emails (currently the "your account was
    # created" welcome mail so a new user can sign in and change their own
    # password). Env-configured, same pattern as the AI key -- no admin UI.
    # If SMTP_HOST is blank the email is skipped gracefully (best-effort).
    # PUBLIC_BASE_URL is the externally reachable base used to build the login
    # link in emails (e.g. https://openmailroom.example.com); blank falls back
    # to the incoming request's own host.
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="noreply@openmailroom.local", alias="SMTP_FROM")
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")
    # Convenience one-var setup for Resend (https://resend.com): setting just
    # RESEND_API_KEY (+ SMTP_FROM on your verified domain) is enough -- the
    # host/port/username are fixed. An explicit SMTP_HOST always overrides
    # this, so any other provider / self-hosted SMTP still works unchanged.
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")

    @model_validator(mode="after")
    def _resolve_data_dependent_defaults(self) -> Settings:
        """Fill in DATA_DIR-relative defaults for database_url/upload_dir.

        Only touches these fields when they're still exactly the
        hardcoded local-dev default (i.e. the deployer didn't set
        DATABASE_URL / UPLOAD_DIR explicitly) -- an explicit override always
        wins, regardless of whether DATA_DIR is usable.
        """
        data_dir_usable = _data_dir_usable(self.data_dir)
        if self.database_url == _LOCAL_DATABASE_URL_DEFAULT and data_dir_usable:
            self.database_url = f"sqlite+aiosqlite:///{self.data_dir.rstrip('/')}/openmailroom.db"
        if self.upload_dir == _LOCAL_UPLOAD_DIR_DEFAULT and data_dir_usable:
            self.upload_dir = f"{self.data_dir.rstrip('/')}/uploads"
        return self

    def require_secret_key(self) -> str:
        if not self.secret_key:
            raise RuntimeError(
                "SECRET_KEY is not set. Provide it via environment variable or .env file."
            )
        return self.secret_key

    def require_encryption_key(self) -> str:
        if not self.encryption_key:
            raise RuntimeError(
                "ENCRYPTION_KEY is not set. Provide it via environment variable or .env file."
            )
        return self.encryption_key

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_branding(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load config/branding.yaml, merged on top of built-in defaults.

    Never raises: any I/O or parse error silently falls back to defaults so a
    missing or broken branding file cannot take the whole app down.
    """
    branding_path = Path(path) if path is not None else DEFAULT_BRANDING_PATH
    try:
        if branding_path.is_file():
            with branding_path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                return _deep_merge(DEFAULT_BRANDING, loaded)
    except Exception:
        # Intentionally swallow: branding is cosmetic, never fatal.
        pass
    return dict(DEFAULT_BRANDING)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_branding() -> dict[str, Any]:
    return load_branding(get_settings().branding_path)


def reset_settings_cache() -> None:
    """Used by tests to force Settings/branding to be re-read after env changes."""
    get_settings.cache_clear()
    get_branding.cache_clear()
