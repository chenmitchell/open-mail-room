"""SMTP email adapter (stdlib smtplib, run in a thread-pool executor so it
never blocks the event loop -- 05-NOTIFICATIONS.md section 2: "email: SMTP
(host/port/tls 設定);stdlib smtplib 丟 executor 即可").
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.notify.base import RenderedMessage, SendResult


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int = 587
    use_tls: bool = True
    username: str | None = None
    password: str | None = None
    from_addr: str = "noreply@openmailroom.local"


def _send_sync(cfg: SmtpConfig, to_addr: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(cfg.host, cfg.port, timeout=10) as smtp:
        if cfg.use_tls:
            smtp.starttls()
        if cfg.username:
            smtp.login(cfg.username, cfg.password or "")
        smtp.send_message(msg)


class EmailAdapter:
    slug = "email"

    def __init__(self, *, config: SmtpConfig, subject: str = "Open Mail Room 通知") -> None:
        self._config = config
        self._subject = subject

    async def send(self, binding, message: RenderedMessage) -> SendResult:
        if not self._config.host:
            return SendResult(ok=False, error="SMTP host is not configured")
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                _send_sync,
                self._config,
                binding.address,
                message.title or self._subject,
                message.text,
            )
        except (
            smtplib.SMTPException,
            OSError,
        ) as exc:  # noqa: BLE001 - broad on purpose, any SMTP failure is a delivery failure
            return SendResult(ok=False, error=f"SMTP send failed: {exc}")
        return SendResult(ok=True)
