"""M9-BE: host-env-var AI key fallback (app/ocr/pipeline.py's
`_env_fallback_provider_configs`), the per-day request cap
(`count_ocr_jobs_today`/`effective_daily_request_limit`), and the admin
`GET|PUT /admin/ai/status|models|settings` endpoints
(app/api/v1/ai_settings.py). All AI calls are mocked at the
`httpx.AsyncClient.get`/`.post` layer -- 不打真實 AI API.
"""

from __future__ import annotations

import io
import json as _json

import httpx
from sqlalchemy import select

from app.config import reset_settings_cache
from app.models.ai_provider_config import AiProviderConfig
from app.models.attachment import Attachment
from app.models.audit_log import AuditLog
from app.models.enums import AiProvider, AttachmentKind, AttachmentOwnerType, UserRole
from app.security.file_crypto import save_encrypted_file
from tests._helpers import drain_background_ocr_tasks, login_as


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


async def _make_provider(db_session, *, provider: AiProvider, priority: int, **kwargs):
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


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)

    def json(self):
        return self._data


def _openai_success_response(tracking_no="1234567890AB"):
    content = {"tracking_no": tracking_no, "carrier_guess": "tcat", "confidence": 0.9}
    return {
        "choices": [{"message": {"content": _json.dumps(content, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _google_models_payload(*names_with_generate_content):
    return {
        "models": [
            {
                "name": f"models/{name}",
                "supportedGenerationMethods": ["generateContent"],
            }
            for name in names_with_generate_content
        ]
    }


def _google_generate_content_response(tracking_no="1234567890AB"):
    content = {"tracking_no": tracking_no, "carrier_guess": "tcat", "confidence": 0.9}
    return {
        "candidates": [
            {"content": {"parts": [{"text": _json.dumps(content, ensure_ascii=False)}]}}
        ],
        "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 10},
    }


# --- 1. env-var provider fallback (no active ai_provider_configs row) -----


async def test_env_fallback_provider_used_when_no_db_config(client, db_session, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "sk-env-test-key")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_MODEL", "gpt-4o-mini")
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            assert headers["Authorization"] == "Bearer sk-env-test-key"
            return _FakeResponse(_openai_success_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    body = resp.json()["data"]
    assert body["status"] == "succeeded", body
    assert body["provider"] == "env"
    assert body["model"] == "gpt-4o-mini"


async def test_env_fallback_not_used_when_db_config_active(client, db_session, monkeypatch):
    """A DB-managed `ai_provider_configs` row always wins over the env-var
    fallback -- the fallback only kicks in when `_active_provider_configs`
    comes back empty."""
    monkeypatch.setenv("AI_API_KEY", "sk-env-should-not-be-used")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            assert headers["Authorization"] == "Bearer sk-openai-testkey"
            return _FakeResponse(_openai_success_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    body = resp.json()["data"]
    assert body["status"] == "succeeded", body
    assert body["provider"] != "env"


async def test_env_fallback_google_model_auto_resolved(client, db_session, monkeypatch):
    """No AI_MODEL set -> pipeline calls resolve_google_model (ListModels)
    and picks a vision-capable flash model the key actually supports."""
    monkeypatch.setenv("AI_API_KEY", "sk-google-test-key")
    monkeypatch.setenv("AI_PROVIDER", "google")
    monkeypatch.delenv("AI_MODEL", raising=False)
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)

    orig_get = httpx.AsyncClient.get
    orig_post = httpx.AsyncClient.post

    async def fake_get(self, url, **kwargs):
        if isinstance(url, str) and "generativelanguage.googleapis.com" in url:
            return _FakeResponse(_google_models_payload("gemini-flash-latest", "gemini-1.5-flash"))
        return await orig_get(self, url, **kwargs)

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "generativelanguage.googleapis.com" in url:
            return _FakeResponse(_google_generate_content_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    body = resp.json()["data"]
    assert body["status"] == "succeeded", body
    assert body["provider"] == "env"
    # resolve_google_model deprioritizes the overloaded *-latest alias, so from
    # the two available models it picks the stable gemini-1.5-flash.
    assert body["model"] == "gemini-1.5-flash"


async def test_no_provider_error_hints_env_var(client, db_session):
    """No DB config and no env key -> the failure message now points the
    counter/admin at the two ways to fix it."""
    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
    body = resp.json()["data"]
    assert body["status"] == "failed"
    assert "AI_API_KEY" in body["error"]
    assert "GEMINI_API_KEY" in body["error"]


# --- 2. daily request cap ---------------------------------------------------


async def test_daily_request_limit_blocks_after_limit_reached(client, db_session, monkeypatch):
    monkeypatch.setenv("AI_DAILY_REQUEST_LIMIT", "2")
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.counter)
    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            return _FakeResponse(_openai_success_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    job_ids = []
    for _ in range(2):
        resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
        assert resp.status_code == 201
        job_ids.append(resp.json()["data"]["id"])
        await drain_background_ocr_tasks()

    for job_id in job_ids:
        resp = await client.get(f"/api/v1/ocr/jobs/{job_id}")
        assert resp.json()["data"]["status"] == "succeeded"

    # 3rd job of the day: used_today (2) >= limit (2) -> blocked before any
    # provider is even attempted.
    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    assert resp.status_code == 201
    third_job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()

    resp = await client.get(f"/api/v1/ocr/jobs/{third_job_id}")
    body = resp.json()["data"]
    assert body["status"] == "failed"
    assert "已達每日 AI 請求上限" in body["error"]


async def test_daily_request_limit_uses_settings_table_override(client, db_session, monkeypatch):
    """A `PUT /admin/ai/settings` override in the `settings` table wins over
    the env var default."""
    monkeypatch.setenv("AI_DAILY_REQUEST_LIMIT", "10000")
    reset_settings_cache()

    admin = await login_as(client, db_session, role=UserRole.admin)
    resp = await client.put("/api/v1/admin/ai/settings", json={"daily_request_limit": 1})
    assert resp.status_code == 200, resp.text

    attachment = await _make_attachment(db_session)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, headers=None, **kwargs):
        if isinstance(url, str) and "api.openai.com" in url:
            return _FakeResponse(_openai_success_response())
        return await orig_post(self, url, json=json, headers=headers, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    first_job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()
    resp = await client.get(f"/api/v1/ocr/jobs/{first_job_id}")
    assert resp.json()["data"]["status"] == "succeeded"

    resp = await client.post("/api/v1/ocr/jobs", json={"attachment_ids": [attachment.id]})
    second_job_id = resp.json()["data"]["id"]
    await drain_background_ocr_tasks()
    resp = await client.get(f"/api/v1/ocr/jobs/{second_job_id}")
    body = resp.json()["data"]
    assert body["status"] == "failed"
    assert "已達每日 AI 請求上限" in body["error"]
    del admin  # only needed to log in as admin for the PUT above


# --- 3. GET /admin/ai/status -------------------------------------------------


async def test_ai_status_reports_env_key_and_usage(client, db_session, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "sk-status-test")
    monkeypatch.setenv("AI_PROVIDER", "google")
    monkeypatch.setenv("AI_MODEL", "")
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.get("/api/v1/admin/ai/status")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data == {
        "env_key_present": True,
        "provider": "google",
        "effective_model": "",
        "daily_request_limit": 10000,
        "used_today": 0,
        "has_db_config": False,
    }


async def test_ai_status_reflects_db_config_and_used_today(client, db_session, monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.admin)
    await _make_provider(db_session, provider=AiProvider.openai, priority=0)

    resp = await client.get("/api/v1/admin/ai/status")
    data = resp.json()["data"]
    assert data["env_key_present"] is False
    assert data["has_db_config"] is True


async def test_ai_status_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.get("/api/v1/admin/ai/status")
    assert resp.status_code == 403


# --- 4. GET /admin/ai/models -------------------------------------------------


async def test_ai_models_endpoint_no_key(client, db_session, monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.get("/api/v1/admin/ai/models")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "AI_NO_KEY"


async def test_ai_models_endpoint_success(client, db_session, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "sk-models-test")
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.admin)

    orig_get = httpx.AsyncClient.get

    async def fake_get(self, url, **kwargs):
        if isinstance(url, str) and "generativelanguage.googleapis.com" in url:
            return _FakeResponse(
                {
                    "models": [
                        {
                            "name": "models/gemini-flash-latest",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/embedding-001",
                            "supportedGenerationMethods": ["embedContent"],
                        },
                    ]
                }
            )
        return await orig_get(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    resp = await client.get("/api/v1/admin/ai/models")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["models"] == ["gemini-flash-latest"]


async def test_ai_models_endpoint_upstream_failure(client, db_session, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "sk-models-test")
    reset_settings_cache()

    await login_as(client, db_session, role=UserRole.admin)

    orig_get = httpx.AsyncClient.get

    async def fake_get(self, url, **kwargs):
        if isinstance(url, str) and "generativelanguage.googleapis.com" in url:
            return _FakeResponse({}, status_code=500)
        return await orig_get(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    resp = await client.get("/api/v1/admin/ai/models")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "AI_MODELS_UNAVAILABLE"


async def test_ai_models_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.get("/api/v1/admin/ai/models")
    assert resp.status_code == 403


# --- 5. PUT /admin/ai/settings -----------------------------------------------


async def test_put_ai_settings_updates_model_and_limit(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.put(
        "/api/v1/admin/ai/settings",
        json={"model": "gemini-2.5-flash", "daily_request_limit": 500},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["effective_model"] == "gemini-2.5-flash"
    assert data["daily_request_limit"] == 500

    resp2 = await client.get("/api/v1/admin/ai/status")
    data2 = resp2.json()["data"]
    assert data2["effective_model"] == "gemini-2.5-flash"
    assert data2["daily_request_limit"] == 500

    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "ai_settings.update")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_put_ai_settings_clears_model_override(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    await client.put("/api/v1/admin/ai/settings", json={"model": "gemini-2.5-flash"})

    resp = await client.put("/api/v1/admin/ai/settings", json={"model": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["effective_model"] == ""


async def test_put_ai_settings_rejects_out_of_range_limit(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.put("/api/v1/admin/ai/settings", json={"daily_request_limit": 0})
    assert resp.status_code == 422

    resp2 = await client.put("/api/v1/admin/ai/settings", json={"daily_request_limit": 200000})
    assert resp2.status_code == 422


async def test_put_ai_settings_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.put("/api/v1/admin/ai/settings", json={"daily_request_limit": 500})
    assert resp.status_code == 403
