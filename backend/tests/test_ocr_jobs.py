"""POST /ocr/jobs, GET /ocr/jobs/{id}, GET /ocr/jobs/{id}/draft
(03-API-SPEC.md section 2; 04-AI-OCR.md sections 2/4/5): job creation
validation, confidential-item gating, provider failover + retry, monthly
budget cutoff, and draft assembly (pre-filled fields + employee-match
candidates + barcode fields). All AI calls are mocked at
httpx.AsyncClient.post -- 不打真實 AI API.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.models.ai_provider_config import AiProviderConfig
from app.models.attachment import Attachment
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.enums import (
    AiProvider,
    AttachmentKind,
    AttachmentOwnerType,
    MailStatus,
    MailType,
    OcrStatus,
    UserRole,
)
from app.models.mail_item import MailItem
from app.models.ocr_job import OcrJob
from app.security.file_crypto import save_encrypted_file
from tests._helpers import create_user, drain_background_ocr_tasks, login, login_as


def _tiny_jpeg() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color=(10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


async def _make_attachment(db_session) -> Attachment:
    stored = save_encrypted_file(_tiny_jpeg(), subdir="mail_photos/pending", extension="jpg")
    attachment = Attachment(
        owner_type=AttachmentOwnerType.mail_item,
        owner_id="placeholder",
        kind=AttachmentKind.label_photo,
        file_path=stored["file_path"],
        sha256=stored["sha256"],
        mime="image/jpeg",
        size_bytes=stored["size_bytes"],
        width=40,
        height=30,
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)
    attachment.owner_id = attachment.id
    await db_session.commit()
    return attachment


async def _make_provider(
    db_session, *, provider: AiProvider, priority: int, **kwargs
) -> AiProviderConfig:
    cfg = AiProviderConfig(
        provider=provider,
        api_key_encrypted=f"sk-{provider.value}-testkey",
        model="test-model",
        priority=priority,
        is_active=True,
        **kwargs,
    )
    db_session.add(cfg)
    await db_session.commit()
    await db_session.refresh(cfg)
    return cfg


def _openai_success_response(tracking_no="1234567890AB", carrier_guess="tcat", recipient_name=None):
    content = {
        "tracking_no": tracking_no,
        "carrier_guess": carrier_guess,
        "confidence": 0.9,
    }
    if recipient_name is not None:
        content["recipient_name"] = recipient_name
    import json as _json

    return {
        "choices": [{"message": {"content": _json.dumps(content, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 40},
    }


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)

    def json(self):
        return self._data


async def test_create_job_rejects_empty_attachment_ids(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": []})
    assert resp.status_code == 422


async def test_create_job_rejects_unknown_attachment(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": ["nope"]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ATTACHMENT_NOT_FOUND"


async def test_create_job_requires_counter_or_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)
    attachment = await _make_attachment(db_session)
    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    assert resp.status_code == 403


async def test_create_job_rejects_explicit_confidential_flag(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    resp = await client.post(
        "/api/v1/ocr/jobs",
        json={"attachment_ids": [attachment.id], "is_confidential": True},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "OCR_CONFIDENTIAL_DISABLED"


async def test_create_job_rejects_attachment_linked_to_confidential_item(client, db_session):
    admin = await login_as(client, db_session, role=UserRole.admin)
    item = MailItem(
        item_no="IN-20260711-0002",
        direction="inbound",
        mail_type=MailType.parcel,
        recipient_name_raw="X",
        received_at=datetime.now(timezone.utc),
        received_by=admin.id,
        status=MailStatus.received,
        is_confidential=True,
    )
    db_session.add(item)
    await db_session.commit()

    stored = save_encrypted_file(_tiny_jpeg(), subdir="mail_photos/pending", extension="jpg")
    attachment = Attachment(
        owner_type=AttachmentOwnerType.mail_item,
        owner_id=item.id,
        kind=AttachmentKind.label_photo,
        file_path=stored["file_path"],
        sha256=stored["sha256"],
        mime="image/jpeg",
        size_bytes=stored["size_bytes"],
        width=40,
        height=30,
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "OCR_CONFIDENTIAL_DISABLED"


async def test_get_job_not_found(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.get("/api/v1/ocr/jobs/does-not-exist")
    assert resp.status_code == 404


async def test_job_fails_when_no_active_provider_configured(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["data"]["id"]

    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    body = resp.json()["data"]
    assert body["status"] == "failed"
    assert "No active AI provider" in body["error"]


async def test_job_succeeds_first_try(client, db_session, monkeypatch):
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        # `client` (the ASGI test client) is itself an httpx.AsyncClient, so
        # this patch also intercepts its own requests to the test server --
        # only fake calls that are actually headed at the (simulated) AI
        # provider host, and pass everything else through untouched.
        if isinstance(url, str) and "api.openai.com" in url:
            return _FakeResponse(_openai_success_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    body = resp.json()["data"]
    assert body["status"] == "succeeded"
    assert body["retries"] == 0
    assert body["cost_estimate"] > 0
    assert body["prompt_version"] == "v3"


async def test_job_failover_to_second_provider_after_first_exhausts_retries(
    client, db_session, monkeypatch
):
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)
    await _make_provider(db_session, provider=AiProvider.anthropic, priority=1)

    call_counts = {"openai": 0, "anthropic": 0}
    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            call_counts["openai"] += 1
            raise httpx.ConnectError("simulated network failure")
        if isinstance(url, str) and "api.anthropic.com" in url:
            call_counts["anthropic"] += 1
            return _FakeResponse(
                {
                    "content": [{"text": '{"tracking_no": "9998887770", "confidence": 0.7}'}],
                    "usage": {"input_tokens": 50, "output_tokens": 10},
                }
            )
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    assert call_counts["openai"] == 3  # MAX_ATTEMPTS_PER_PROVIDER, then failover
    assert call_counts["anthropic"] == 1

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    body = resp.json()["data"]
    assert body["status"] == "succeeded"
    assert body["retries"] == 3


async def test_job_fails_dead_letter_when_all_providers_exhausted(client, db_session, monkeypatch):
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)
    await _make_provider(db_session, provider=AiProvider.anthropic, priority=1)

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and ("api.openai.com" in url or "api.anthropic.com" in url):
            raise httpx.ConnectError("everything is down")
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    body = resp.json()["data"]
    assert body["status"] == "failed"
    assert body["retries"] == 6
    assert body["error"]


async def test_job_success_disables_provider_over_monthly_budget(client, db_session, monkeypatch):
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    cfg = await _make_provider(
        db_session, provider=AiProvider.openai, priority=0, monthly_budget_usd=0.000001
    )

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            return _FakeResponse(_openai_success_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    assert resp.json()["data"]["status"] == "succeeded"

    # A fresh session (rather than reusing the fixture's `db_session`, whose
    # underlying connection was left in an unusable state by interleaving
    # with the background task's own session on the shared StaticPool
    # connection -- the same class of hazard documented in
    # app/ocr/pipeline.py's module docstring) verifies the DB-level effects.
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as verify_session:
        refreshed = await verify_session.get(AiProviderConfig, cfg.id)
        assert refreshed.is_active is False

        audit_rows = (
            (
                await verify_session.execute(
                    select(AuditLog).where(AuditLog.action == "ai_provider.budget_exceeded")
                )
            )
            .scalars()
            .all()
        )
        assert len(audit_rows) == 1
        assert audit_rows[0].target_id == cfg.id


async def test_draft_not_ready_before_job_runs(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    job = OcrJob(attachment_ids=["x"], status=OcrStatus.queued)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    resp = await client.get(f"/api/v1/ocr/jobs/{job.id}/draft")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "queued"
    assert body["draft"]["tracking_no"] is None
    assert body["employee_candidates"] == []


async def test_draft_includes_employee_match_candidates_on_success(client, db_session, monkeypatch):
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)

    employee = Employee(name="陳大文", aliases=[], pickup_code="ZZZZ9999")
    db_session.add(employee)
    await db_session.commit()

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            return _FakeResponse(_openai_success_response(recipient_name="陳大文"))
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post(
        "/api/v1/ocr/jobs",
        json={"attachment_ids": [attachment.id], "barcode_hints": {attachment.id: "1Z999"}},
    )
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}/draft")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["status"] == "succeeded"
    assert body["draft"]["recipient_name"] == "陳大文"
    # M2-R1 contract gap #4: a barcode hint present at job-creation time wins
    # over the AI's own tracking_no guess *server-side*, in the persisted
    # result_json -- not just in the frontend's transient pre-fill logic.
    assert body["draft"]["tracking_no"] == "1Z999"
    candidates = body["employee_candidates"]
    assert any(c["employee_id"] == employee.id for c in candidates)
    assert body["barcode_results"] == {attachment.id: "1Z999"}


async def test_draft_forbidden_for_viewer_pending_attachment(client, db_session, monkeypatch):
    """M2-R1 contract gap #5: 補機密件 gating(鏡射 uploads.py) -- every
    attachment an OCR job covers is still "pending" (unconfirmed) at
    draft-review time, so a `viewer` (not admin/counter) must be blocked the
    same way `GET /uploads/{id}` already blocks them for a pending photo."""
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            return _FakeResponse(_openai_success_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    await create_user(db_session, email="viewer-ocr@example.com", role=UserRole.viewer)
    await login(client, email="viewer-ocr@example.com")

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}/draft")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_draft_allowed_for_counter_pending_attachment(client, db_session, monkeypatch):
    """The counter role that created the job (and is therefore allowed to
    have created the still-pending attachment in the first place) is not
    blocked by the M2-R1 gap #5 gating -- only stricter than admin/counter
    roles are."""
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            return _FakeResponse(_openai_success_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}/draft")
    assert resp.status_code == 200


async def test_draft_forbidden_for_viewer_when_linked_to_confidential_item(client, db_session):
    """Re-run-OCR scenario: the job's attachment is already linked to a
    confirmed confidential mail_item -- a viewer must still be blocked, and
    admin/counter must still be allowed (mirrors
    test_get_upload_linked_to_confidential_item_restricted in test_uploads.py)."""
    admin = await login_as(client, db_session, role=UserRole.admin)
    item = MailItem(
        item_no="IN-20260711-0003",
        direction="inbound",
        mail_type=MailType.parcel,
        recipient_name_raw="X",
        received_at=datetime.now(timezone.utc),
        received_by=admin.id,
        status=MailStatus.received,
        is_confidential=True,
    )
    db_session.add(item)
    await db_session.commit()

    stored = save_encrypted_file(_tiny_jpeg(), subdir="mail_photos/pending", extension="jpg")
    attachment = Attachment(
        owner_type=AttachmentOwnerType.mail_item,
        owner_id=item.id,
        kind=AttachmentKind.label_photo,
        file_path=stored["file_path"],
        sha256=stored["sha256"],
        mime="image/jpeg",
        size_bytes=stored["size_bytes"],
        width=40,
        height=30,
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)

    job = OcrJob(
        attachment_ids=[attachment.id],
        status=OcrStatus.succeeded,
        result_json={"tracking_no": "T1", "confidence": 0.9},
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    await create_user(db_session, email="viewer-conf-ocr@example.com", role=UserRole.viewer)
    await login(client, email="viewer-conf-ocr@example.com")
    resp = await client.get(f"/api/v1/ocr/jobs/{job.id}/draft")
    assert resp.status_code == 403

    await login(client, email=admin.email)
    resp2 = await client.get(f"/api/v1/ocr/jobs/{job.id}/draft")
    assert resp2.status_code == 200


async def test_draft_requires_read_role(client, db_session):
    resp = await client.get("/api/v1/ocr/jobs/anything/draft")
    assert resp.status_code == 401
