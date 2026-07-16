"""Event name constants (03-API-SPEC.md section 3)."""

from __future__ import annotations

EVENT_ITEM_RECEIVED = "item.received"
EVENT_ITEM_NOTIFIED = "item.notified"
EVENT_ITEM_REMINDER = "item.reminder"
EVENT_ITEM_PICKED_UP = "item.picked_up"
EVENT_ITEM_RETURNED = "item.returned"
EVENT_ITEM_UNCLAIMED = "item.unclaimed"
# Constant only in this milestone -- actually publishing it is M4 (outbound
# shipping) scope, per the task brief ("+outbound.shipped 常數,M4 觸發").
EVENT_OUTBOUND_SHIPPED = "outbound.shipped"

ALL_EVENTS = (
    EVENT_ITEM_RECEIVED,
    EVENT_ITEM_NOTIFIED,
    EVENT_ITEM_REMINDER,
    EVENT_ITEM_PICKED_UP,
    EVENT_ITEM_RETURNED,
    EVENT_ITEM_UNCLAIMED,
    EVENT_OUTBOUND_SHIPPED,
)
