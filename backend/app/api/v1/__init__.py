from fastapi import APIRouter

from app.api.v1.admin_audit import router as admin_audit_router
from app.api.v1.admin_users import router as admin_users_router
from app.api.v1.admin_webhooks import router as admin_webhooks_router
from app.api.v1.ai_providers import router as ai_providers_router
from app.api.v1.ai_settings import router as ai_settings_router
from app.api.v1.auth import router as auth_router
from app.api.v1.bindings import router as bindings_router
from app.api.v1.carriers import router as carriers_router
from app.api.v1.channel_webhooks import router as channel_webhooks_router
from app.api.v1.departments import router as departments_router
from app.api.v1.employees import router as employees_router
from app.api.v1.exports import router as exports_router
from app.api.v1.mail_items import router as mail_items_router
from app.api.v1.me_items import router as me_items_router
from app.api.v1.notifications import notifications_list_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.ocr_jobs import router as ocr_jobs_router
from app.api.v1.outbound import router as outbound_router
from app.api.v1.pickup import router as pickup_router
from app.api.v1.reports import router as reports_router
from app.api.v1.setup import router as setup_router
from app.api.v1.uploads import router as uploads_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(setup_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(carriers_router)
api_v1_router.include_router(departments_router)
api_v1_router.include_router(employees_router)
api_v1_router.include_router(mail_items_router)
api_v1_router.include_router(me_items_router)
api_v1_router.include_router(pickup_router)
api_v1_router.include_router(uploads_router)
api_v1_router.include_router(ocr_jobs_router)
api_v1_router.include_router(ai_providers_router)
api_v1_router.include_router(ai_settings_router)
api_v1_router.include_router(bindings_router)
api_v1_router.include_router(channel_webhooks_router)
api_v1_router.include_router(admin_webhooks_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(notifications_list_router)
api_v1_router.include_router(outbound_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(exports_router)
api_v1_router.include_router(admin_audit_router)
api_v1_router.include_router(admin_users_router)

__all__ = ["api_v1_router"]
