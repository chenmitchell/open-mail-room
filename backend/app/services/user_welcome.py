"""Best-effort welcome email for a newly created login account, so the user
can sign in and change their own password (app/api/v1/admin_users.create_user).

Reuses the notification system's SMTP EmailAdapter, but configured from host
env vars (app/config.py SMTP_*), because this is a *system* email, not a
per-user notification binding. If SMTP is unconfigured (SMTP_HOST blank) or
delivery fails, this returns False and never raises -- creating the account
must succeed regardless of email delivery.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from app.config import get_settings
from app.notify.adapters.email import EmailAdapter, SmtpConfig
from app.notify.base import RenderedMessage

logger = logging.getLogger(__name__)


def _smtp_config_from_env() -> SmtpConfig | None:
    s = get_settings()
    default_from = "noreply@openmailroom.local"
    # Explicit generic SMTP (any provider / self-hosted) always wins -- the
    # path open-source adopters use.
    if s.smtp_host:
        return SmtpConfig(
            host=s.smtp_host,
            port=s.smtp_port,
            use_tls=s.smtp_use_tls,
            username=s.smtp_username or None,
            password=s.smtp_password or None,
            from_addr=s.smtp_from or default_from,
        )
    # Convenience: a single RESEND_API_KEY is enough to send via Resend
    # (host/port/username are fixed). Still needs SMTP_FROM set to an address
    # on your Resend-verified domain.
    resend_key = getattr(s, "resend_api_key", "") or ""
    if resend_key:
        return SmtpConfig(
            host="smtp.resend.com",
            port=587,
            use_tls=True,
            username="resend",
            password=resend_key,
            from_addr=s.smtp_from or default_from,
        )
    return None


def build_welcome_message(
    *, display_name: str, email: str, initial_password: str, login_url: str
) -> RenderedMessage:
    title = "Open Mail Room 帳號已建立"
    text = (
        f"{display_name} 您好,\n\n"
        "您的 Open Mail Room 收發室系統帳號已由管理員建立,以下是登入資訊:\n\n"
        f"登入網址:{login_url}\n"
        f"帳號(電子郵件):{email}\n"
        f"初始密碼:{initial_password}\n\n"
        "為了帳號安全,請於首次登入後立即修改密碼"
        "(登入後點右上角選單的『修改密碼』)。\n\n"
        "若您並未預期收到此信,請聯繫系統管理員。\n"
    )
    return RenderedMessage(text=text, title=title)


async def send_welcome_email(
    *, email: str, display_name: str, initial_password: str, login_url: str
) -> bool:
    cfg = _smtp_config_from_env()
    if cfg is None:
        logger.info("welcome email skipped: SMTP not configured (SMTP_HOST empty)")
        return False
    adapter = EmailAdapter(config=cfg)
    message = build_welcome_message(
        display_name=display_name,
        email=email,
        initial_password=initial_password,
        login_url=login_url,
    )
    # EmailAdapter.send only reads `.address` off the binding; a duck-typed
    # stand-in avoids needing a real NotificationBinding row for a system email.
    binding = SimpleNamespace(address=email)
    try:
        result = await adapter.send(binding, message)
    except Exception as exc:  # noqa: BLE001 - best-effort, never break account creation
        logger.warning("welcome email send raised: %r", exc)
        return False
    if not result.ok:
        logger.warning("welcome email not delivered: %s", result.error)
    return result.ok
