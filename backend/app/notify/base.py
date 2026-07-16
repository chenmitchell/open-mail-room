"""`NotifyChannel` adapter protocol (05-NOTIFICATIONS.md section 2):

    class NotifyChannel(Protocol):
        slug: str
        async def send(self, binding, message) -> SendResult: ...

`binding` is the `NotificationBinding` ORM row (its `.address` is already
plaintext -- `Encrypted` decrypts transparently on read); `message` is a
`RenderedMessage` produced by app/notify/templates.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.models.notification_binding import NotificationBinding


@dataclass(frozen=True)
class RenderedMessage:
    text: str
    title: str | None = None


@dataclass(frozen=True)
class SendResult:
    ok: bool
    error: str | None = None
    provider_message_id: str | None = None


class NotifyChannel(Protocol):
    slug: str

    async def send(
        self, binding: NotificationBinding, message: RenderedMessage
    ) -> SendResult: ...
