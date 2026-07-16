"""Message template rendering (05-NOTIFICATIONS.md section 4).

Precedence for a given template name: admin override in the `settings` table
(key "notify.templates", a dict) > `config/branding.yaml` override (loaded
via `app.config.get_branding()`) > built-in default
(`app.config.DEFAULT_BRANDING`).

Confidential masking: whenever `is_confidential` is True, `received` is
swapped for `received_confidential` (a template with no sender/content
variables in its default text) *and*, belt-and-suspenders, the `sender`
variable itself is always rendered as an empty string -- so even a
misconfigured admin override of `received` that still references `{sender}`
can never leak it for a confidential item.
"""

from __future__ import annotations

from typing import Any

from app.config import DEFAULT_BRANDING, get_branding
from app.models.employee import Employee
from app.models.enums import NotificationTemplate
from app.models.mail_item import MailItem
from app.notify.base import RenderedMessage
from app.notify.settings_store import get_dict_setting


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:  # noqa: ARG002 - Mapping protocol requires the arg
        return ""


def render_string(text: str, variables: dict[str, Any]) -> str:
    safe = _SafeDict({k: ("" if v is None else v) for k, v in variables.items()})
    try:
        return text.format_map(safe)
    except (KeyError, ValueError, IndexError):
        # A malformed admin-authored override (stray `{` etc.) must never
        # crash delivery -- fall back to the raw text rather than 500ing.
        return text


def _default_template(name: str) -> str:
    templates = DEFAULT_BRANDING["notification_templates"]
    return templates.get(name, "")


async def resolve_template_text(session, name: str) -> str:
    """name is one of: received, received_confidential, reminder, overdue,
    outbound_shipped."""
    overrides = await get_dict_setting(session, "notify.templates")
    if name in overrides and overrides[name]:
        return str(overrides[name])

    branding = get_branding()
    branding_templates = branding.get("notification_templates") or {}
    if name in branding_templates and branding_templates[name]:
        return str(branding_templates[name])

    return _default_template(name)


def _template_name_for(template: NotificationTemplate, *, is_confidential: bool) -> str:
    if template == NotificationTemplate.received:
        return "received_confidential" if is_confidential else "received"
    return template.value


async def render_notification(
    session,
    *,
    template: NotificationTemplate,
    mail_item: MailItem,
    employee: Employee | None,
    days: int | None = None,
) -> RenderedMessage:
    branding = get_branding()
    is_confidential = bool(mail_item.is_confidential)
    name = _template_name_for(template, is_confidential=is_confidential)
    text = await resolve_template_text(session, name)

    variables: dict[str, Any] = {
        "mail_type": mail_item.mail_type.value if mail_item.mail_type else "",
        # Confidential masking: never interpolate the real sender, no matter
        # which template text ends up being used.
        "sender": "" if is_confidential else (mail_item.sender_org or mail_item.sender_name or ""),
        "tracking_no": mail_item.tracking_no or "",
        "pickup_code": (employee.pickup_code if employee else None) or "",
        "pickup_location": branding.get("pickup_location") or "",
        "item_no": mail_item.item_no or "",
        "recipient_name": (employee.name if employee else None)
        or mail_item.recipient_name_raw
        or "",
        "days": days if days is not None else "",
    }
    return RenderedMessage(text=render_string(text, variables))


async def render_outbound_shipped(
    session, *, tracking_no: str | None, item_no: str
) -> RenderedMessage:
    text = await resolve_template_text(session, "outbound_shipped")
    return RenderedMessage(
        text=render_string(text, {"tracking_no": tracking_no or "", "item_no": item_no})
    )
