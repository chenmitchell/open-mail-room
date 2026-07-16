"""GET /api/v1/admin/audit-logs -- admin-only, paginated, filterable
(01-REQUIREMENTS.md role table: "admin: ... 稽核紀錄")."""

from __future__ import annotations

from app.models.enums import UserRole
from tests._helpers import create_user, login, login_as


async def test_audit_logs_requires_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.get("/api/v1/admin/audit-logs")
    assert resp.status_code == 403


async def test_audit_logs_lists_actions_from_writes(client, db_session):
    await login_as(client, db_session, role=UserRole.admin, email="admin-audit@example.com")

    created = (
        await client.post("/api/v1/outbound", json={"to_name": "王小明"})
    ).json()["data"]
    await client.post(f"/api/v1/outbound/{created['id']}/shipped", json={})

    resp = await client.get("/api/v1/admin/audit-logs")
    assert resp.status_code == 200
    body = resp.json()
    actions = {row["action"] for row in body["data"]}
    assert "outbound_item.create" in actions
    assert "outbound_item.shipped" in actions
    assert body["meta"]["total"] >= 2


async def test_audit_logs_filter_by_action(client, db_session):
    await login_as(client, db_session, role=UserRole.admin, email="admin-audit2@example.com")
    await client.post("/api/v1/outbound", json={"to_name": "A"})
    await client.post("/api/v1/outbound", json={"to_name": "B"})

    resp = await client.get("/api/v1/admin/audit-logs?action=outbound_item.create")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 2
    assert all(row["action"] == "outbound_item.create" for row in body["data"])


async def test_audit_logs_filter_by_target(client, db_session):
    await login_as(client, db_session, role=UserRole.admin, email="admin-audit3@example.com")
    created = (
        await client.post("/api/v1/outbound", json={"to_name": "A"})
    ).json()["data"]
    await client.post("/api/v1/outbound", json={"to_name": "B"})

    resp = await client.get(
        f"/api/v1/admin/audit-logs?target_type=outbound_item&target_id={created['id']}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["target_id"] == created["id"]


async def test_audit_logs_filter_by_actor(client, db_session):
    admin_user = await login_as(
        client, db_session, role=UserRole.admin, email="admin-audit4@example.com"
    )
    await client.post("/api/v1/outbound", json={"to_name": "A"})

    other_admin = await create_user(
        db_session, email="admin-audit5@example.com", role=UserRole.admin
    )
    await login(client, email="admin-audit5@example.com")
    await client.post("/api/v1/outbound", json={"to_name": "B"})

    resp = await client.get(f"/api/v1/admin/audit-logs?actor_id={admin_user.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert all(row["actor_id"] == admin_user.id for row in body["data"])
    assert body["meta"]["total"] >= 1
    assert other_admin.id != admin_user.id


async def test_audit_logs_pagination(client, db_session):
    await login_as(client, db_session, role=UserRole.admin, email="admin-audit6@example.com")
    for i in range(5):
        await client.post("/api/v1/outbound", json={"to_name": f"item-{i}"})

    resp = await client.get("/api/v1/admin/audit-logs?page=1&size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["meta"]["page"] == 1
    assert body["meta"]["size"] == 2
    assert body["meta"]["total"] >= 5


async def test_audit_log_resolves_actor_name(client, db_session):
    """An audit trail whose 「操作者」 column is a raw UUID is one nobody reads.
    `audit_logs` stores only actor_id on purpose (append-only; a copied name
    would freeze a name that can change), so the display name is resolved at
    read time."""
    user = await login_as(client, db_session, role=UserRole.admin)
    # Any write produces an audit row attributed to this user.
    resp = await client.post("/api/v1/departments", json={"name": "稽核測試部", "code": "audt"})
    assert resp.status_code == 201

    logs = await client.get("/api/v1/admin/audit-logs")
    assert logs.status_code == 200
    entries = logs.json()["data"]
    mine = [e for e in entries if e["actor_id"] == user.id]
    assert mine, "the write should have produced an audit entry for this user"
    assert mine[0]["actor_name"] == user.display_name
    assert mine[0]["actor_name"] != mine[0]["actor_id"]
