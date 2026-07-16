"""GET|POST|PATCH /admin/ai-providers (03-API-SPEC.md section 2 "管理",
07-SECURITY.md section 3): admin-only, key stored encrypted and never read
back -- only a masked `sk-***abc` preview. Also covers the M2-R1 blocking #1
SSRF guard on `base_url` (app/security/ssrf.py).
"""

from __future__ import annotations

from app.models.enums import UserRole
from tests._helpers import login_as


async def test_create_ai_provider_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={"provider": "openai", "api_key": "sk-abcdefghijklmno"},
    )
    assert resp.status_code == 403


async def test_create_ai_provider_masks_key_in_response(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={
            "provider": "openai",
            "api_key": "sk-abcdefghijklmno",
            "model": "gpt-4o-mini",
            "priority": 1,
            "monthly_budget_usd": 50.0,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["api_key_masked"] == "sk-***mno"
    assert "api_key" not in body
    assert "api_key_encrypted" not in body
    assert body["provider"] == "openai"
    assert body["priority"] == 1
    assert body["monthly_budget_usd"] == 50.0
    assert body["is_active"] is True
    assert body["allow_private_network"] is False


async def test_list_ai_providers_never_leaks_raw_key(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    await client.post(
        "/api/v1/admin/ai-providers",
        json={"provider": "anthropic", "api_key": "sk-ant-secretvalue123", "priority": 0},
    )
    resp = await client.get("/api/v1/admin/ai-providers")
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert len(rows) == 1
    assert "secretvalue123" not in resp.text
    assert rows[0]["api_key_masked"].startswith("sk-")


async def test_patch_ai_provider_updates_fields_without_changing_key(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    create_resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={"provider": "google", "api_key": "AIzaSyOriginalKeyValue", "priority": 5},
    )
    config_id = create_resp.json()["data"]["id"]
    original_masked = create_resp.json()["data"]["api_key_masked"]

    resp = await client.patch(
        f"/api/v1/admin/ai-providers/{config_id}",
        json={"priority": 2, "is_active": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["priority"] == 2
    assert body["is_active"] is False
    assert body["api_key_masked"] == original_masked


async def test_patch_ai_provider_can_rotate_key(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    create_resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={"provider": "openrouter", "api_key": "sk-or-oldvalue000", "priority": 0},
    )
    config_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/ai-providers/{config_id}", json={"api_key": "sk-or-newvalue999"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["api_key_masked"] == "sk-***999"

    # The DB-level ciphertext actually changed (not just the response).
    from app.models.ai_provider_config import AiProviderConfig

    db_session.expire_all()
    cfg = await db_session.get(AiProviderConfig, config_id)
    assert cfg.api_key_encrypted == "sk-or-newvalue999"


async def test_patch_ai_provider_not_found(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.patch("/api/v1/admin/ai-providers/does-not-exist", json={"priority": 1})
    assert resp.status_code == 404


async def test_ai_providers_require_csrf_header(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={"provider": "openai", "api_key": "sk-abcdefghijklmno"},
        headers={"x-csrf-token": "wrong-value"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_INVALID"


# ---------------------------------------------------------------------------
# M2-R1 blocking #1: SSRF guard on base_url (app/security/ssrf.py). Every
# case below uses a *literal IP* in base_url (never a hostname) so these
# tests never depend on real DNS resolution being available in the test
# sandbox -- see app/security/ssrf.py's own best-effort-DNS comment for why
# a hostname lookup failure is deliberately non-fatal there.
# ---------------------------------------------------------------------------


async def test_create_ai_provider_rejects_loopback_base_url_by_default(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-local-testkey",
            "base_url": "http://127.0.0.1:11434/v1",
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "AI_PROVIDER_UNSAFE_BASE_URL"


async def test_create_ai_provider_rejects_cloud_metadata_base_url(client, db_session):
    """169.254.169.254 -- the canonical cloud-provider instance-metadata
    endpoint SSRF target -- must be rejected even though it is "only"
    link-local, not RFC1918."""
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-local-testkey",
            "base_url": "http://169.254.169.254/latest/meta-data/",
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "AI_PROVIDER_UNSAFE_BASE_URL"


async def test_create_ai_provider_rejects_rfc1918_base_url(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    for private_host in ("10.0.0.5", "172.16.0.5", "192.168.1.20"):
        resp = await client.post(
            "/api/v1/admin/ai-providers",
            json={
                "provider": "openai_compatible",
                "api_key": "sk-local-testkey",
                "base_url": f"http://{private_host}:11434/v1",
            },
        )
        assert resp.status_code == 400, f"{private_host}: {resp.text}"
        assert resp.json()["error"]["code"] == "AI_PROVIDER_UNSAFE_BASE_URL"


async def test_create_ai_provider_allows_public_base_url_by_default(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-public-testkey",
            "base_url": "http://8.8.8.8/v1",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["allow_private_network"] is False


async def test_create_ai_provider_allows_private_base_url_with_opt_in_flag(client, db_session):
    """04-AI-OCR.md sections 2/5's documented local-Ollama deployment mode."""
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-local-testkey",
            "base_url": "http://192.168.1.20:11434/v1",
            "allow_private_network": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["allow_private_network"] is True
    assert body["base_url"] == "http://192.168.1.20:11434/v1"


async def test_create_ai_provider_with_no_base_url_is_never_ssrf_checked(client, db_session):
    """Anthropic/Google have no configurable base_url -- omitting it must
    never trip the guard."""
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={"provider": "anthropic", "api_key": "sk-ant-testkey"},
    )
    assert resp.status_code == 201, resp.text


async def test_patch_rejects_base_url_change_to_private_without_flag(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    create_resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-public-testkey",
            "base_url": "http://8.8.8.8/v1",
        },
    )
    config_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/ai-providers/{config_id}",
        json={"base_url": "http://10.0.0.9/v1"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "AI_PROVIDER_UNSAFE_BASE_URL"

    # Rejected in-place: the old (safe) base_url must still be what's stored.
    from app.models.ai_provider_config import AiProviderConfig

    db_session.expire_all()
    cfg = await db_session.get(AiProviderConfig, config_id)
    assert cfg.base_url == "http://8.8.8.8/v1"


async def test_patch_ai_provider_allows_private_base_url_once_flag_is_set(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    create_resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-public-testkey",
            "base_url": "http://8.8.8.8/v1",
        },
    )
    config_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/ai-providers/{config_id}",
        json={"base_url": "http://192.168.1.20:11434/v1", "allow_private_network": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["base_url"] == "http://192.168.1.20:11434/v1"
    assert body["allow_private_network"] is True


async def test_patch_rechecks_base_url_when_flag_flipped_off(client, db_session):
    """Re-validates the *effective* pair after a partial PATCH -- flipping
    `allow_private_network` back to False on a config whose base_url is
    already private must re-reject it, not just skip validation because
    base_url itself wasn't part of this particular request."""
    await login_as(client, db_session, role=UserRole.admin)
    create_resp = await client.post(
        "/api/v1/admin/ai-providers",
        json={
            "provider": "openai_compatible",
            "api_key": "sk-local-testkey",
            "base_url": "http://192.168.1.20:11434/v1",
            "allow_private_network": True,
        },
    )
    config_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/ai-providers/{config_id}",
        json={"allow_private_network": False},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "AI_PROVIDER_UNSAFE_BASE_URL"
