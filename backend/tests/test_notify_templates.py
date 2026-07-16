"""Template interpolation + confidential masking (05-NOTIFICATIONS.md
section 4)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.employee import Employee
from app.models.enums import MailStatus, MailType, NotificationTemplate, Refrigeration
from app.models.mail_item import MailItem
from app.notify.settings_store import set_setting
from app.notify.templates import render_notification, render_string


def _mail_item(**overrides) -> MailItem:
    defaults = dict(
        item_no="IN-20260712-0001",
        direction="inbound",
        tracking_no="TRK123",
        mail_type=MailType.parcel,
        sender_name="王先生",
        sender_org="某某公司",
        recipient_name_raw="陳小華",
        received_at=datetime.now(timezone.utc),
        status=MailStatus.received,
        is_confidential=False,
        is_cod=False,
        refrigeration=Refrigeration.none,
    )
    defaults.update(overrides)
    return MailItem(**defaults)


def test_render_string_basic_interpolation():
    text = "寄件:{sender}|單號:{tracking_no}"
    out = render_string(text, {"sender": "ACME", "tracking_no": "T1"})
    assert out == "寄件:ACME|單號:T1"


def test_render_string_missing_variable_becomes_empty():
    out = render_string("hello {missing}", {})
    assert out == "hello "


def test_render_string_malformed_template_falls_back_to_raw_text():
    # A stray unmatched `{` must never crash delivery.
    out = render_string("broken {", {"x": "1"})
    assert out == "broken {"


@pytest.mark.asyncio
async def test_render_notification_interpolates_sender_and_pickup_code(db_session):
    item = _mail_item()
    employee = Employee(name="陳小華", aliases=[], pickup_code="ABC123")

    message = await render_notification(
        db_session, template=NotificationTemplate.received, mail_item=item, employee=employee
    )
    assert "某某公司" in message.text
    assert "ABC123" in message.text
    assert "TRK123" in message.text


@pytest.mark.asyncio
async def test_render_notification_confidential_hides_sender(db_session):
    item = _mail_item(is_confidential=True, sender_org="機密寄件公司", sender_name="機密先生")
    employee = Employee(name="陳小華", aliases=[], pickup_code="XYZ999")

    message = await render_notification(
        db_session, template=NotificationTemplate.received, mail_item=item, employee=employee
    )
    assert "機密寄件公司" not in message.text
    assert "機密先生" not in message.text
    # Confidential default template still surfaces the pickup code so the
    # employee can actually collect it.
    assert "XYZ999" in message.text


@pytest.mark.asyncio
async def test_render_notification_confidential_masks_sender_even_with_custom_override(db_session):
    """Belt-and-suspenders: even if an admin override for `received` (not
    `received_confidential`) still references {sender}, the confidential
    item's sender must never leak -- the `sender` variable itself is always
    forced to "" for confidential mail, independent of *which* template text
    ends up being used."""
    await set_setting(
        db_session,
        "notify.templates",
        {"received_confidential": "件到,寄件人:{sender},請領取"},
    )
    item = _mail_item(is_confidential=True, sender_org="TOP-SECRET-CO")
    employee = Employee(name="X", aliases=[])

    message = await render_notification(
        db_session, template=NotificationTemplate.received, mail_item=item, employee=employee
    )
    assert "TOP-SECRET-CO" not in message.text


@pytest.mark.asyncio
async def test_render_notification_reminder_includes_days(db_session):
    item = _mail_item()
    message = await render_notification(
        db_session,
        template=NotificationTemplate.reminder,
        mail_item=item,
        employee=None,
        days=2,
    )
    assert "2" in message.text


@pytest.mark.asyncio
async def test_render_notification_settings_override_takes_precedence(db_session):
    await set_setting(db_session, "notify.templates", {"received": "CUSTOM {tracking_no}"})
    item = _mail_item()
    employee = Employee(name="X", aliases=[])

    message = await render_notification(
        db_session, template=NotificationTemplate.received, mail_item=item, employee=employee
    )
    assert message.text == "CUSTOM TRK123"
