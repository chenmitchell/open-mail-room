"""Import every model module so `Base.metadata` is fully populated for
Alembic autogenerate and for `Base.metadata.create_all()` in tests.
"""

from app.models.ai_provider_config import AiProviderConfig
from app.models.api_key import ApiKey
from app.models.attachment import Attachment
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.carrier import Carrier
from app.models.department import Department
from app.models.employee import Employee
from app.models.mail_item import MailItem
from app.models.notification import Notification
from app.models.notification_binding import NotificationBinding
from app.models.notification_binding_code import NotificationBindingCode
from app.models.ocr_job import OcrJob
from app.models.outbound_item import OutboundItem
from app.models.setting import Setting
from app.models.user import User
from app.models.webhook_endpoint import WebhookEndpoint

__all__ = [
    "Base",
    "User",
    "Department",
    "Employee",
    "NotificationBinding",
    "NotificationBindingCode",
    "Carrier",
    "MailItem",
    "OutboundItem",
    "Attachment",
    "OcrJob",
    "Notification",
    "WebhookEndpoint",
    "ApiKey",
    "AiProviderConfig",
    "AuditLog",
    "Setting",
]
