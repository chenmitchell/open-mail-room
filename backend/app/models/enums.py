from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    counter = "counter"
    employee = "employee"
    viewer = "viewer"


class EmployeeStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class NotificationChannel(str, enum.Enum):
    line = "line"
    telegram = "telegram"
    slack = "slack"
    discord = "discord"
    email = "email"
    webhook = "webhook"
    webpush = "webpush"


class CarrierKind(str, enum.Enum):
    postal = "postal"
    courier = "courier"
    freight = "freight"
    store = "store"
    messenger = "messenger"
    other = "other"


class MailType(str, enum.Enum):
    letter = "letter"
    document = "document"
    parcel = "parcel"
    box = "box"
    pallet = "pallet"


class Refrigeration(str, enum.Enum):
    none = "none"
    chilled = "chilled"
    frozen = "frozen"


class MailStatus(str, enum.Enum):
    received = "received"
    notified = "notified"
    picked_up = "picked_up"
    returned = "returned"
    forwarded = "forwarded"
    unclaimed = "unclaimed"
    destroyed = "destroyed"


class PickupMethod(str, enum.Enum):
    signature = "signature"
    pickup_code = "pickup_code"
    qr = "qr"


class OutboundPayment(str, enum.Enum):
    company = "company"
    dept_code = "dept_code"
    personal = "personal"


class OutboundStatus(str, enum.Enum):
    pending = "pending"
    shipped = "shipped"
    delivered = "delivered"
    exception = "exception"


class AttachmentOwnerType(str, enum.Enum):
    mail_item = "mail_item"
    outbound_item = "outbound_item"
    pickup = "pickup"


class AttachmentKind(str, enum.Enum):
    label_photo = "label_photo"
    extra_photo = "extra_photo"
    damage_photo = "damage_photo"
    pickup_signature = "pickup_signature"
    pickup_photo = "pickup_photo"


class OcrStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class NotificationTemplate(str, enum.Enum):
    received = "received"
    reminder = "reminder"
    overdue = "overdue"
    # M4-01: outbound-shipped notification to the applicant, sent through the
    # same queued/retry/dead-letter worker (app/notify/worker.py) as the
    # inbound templates -- see app/models/notification.py's
    # `outbound_item_id` column.
    outbound_shipped = "outbound_shipped"


class NotificationStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    failed = "failed"
    dead = "dead"


class AiProvider(str, enum.Enum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    openrouter = "openrouter"
    openai_compatible = "openai_compatible"


class ActorType(str, enum.Enum):
    user = "user"
    api_key = "api_key"
    system = "system"
