from app.models.carrier import Carrier
from app.models.enums import CarrierKind, UserRole
from tests._helpers import login_as


async def _make_carrier(db_session, *, name="黑貓宅急便", slug="tcat") -> Carrier:
    carrier = Carrier(name=name, slug=slug, kind=CarrierKind.courier, is_active=True)
    db_session.add(carrier)
    await db_session.commit()
    await db_session.refresh(carrier)
    return carrier


async def test_list_carriers_requires_auth(client):
    resp = await client.get("/api/v1/carriers")
    assert resp.status_code == 401


async def test_list_carriers_any_authenticated_role(client, db_session):
    await login_as(client, db_session, role=UserRole.viewer)
    await _make_carrier(db_session)

    resp = await client.get("/api/v1/carriers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["meta"]["total"] == 1
    assert body["data"][0]["name"] == "黑貓宅急便"
    assert body["data"][0]["slug"] == "tcat"
    assert body["data"][0]["kind"] == "courier"


async def test_list_carriers_q_filters_by_name(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    await _make_carrier(db_session, name="黑貓宅急便", slug="tcat")
    await _make_carrier(db_session, name="新竹物流", slug="hct")

    resp = await client.get("/api/v1/carriers", params={"q": "黑貓"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["slug"] == "tcat"


async def test_list_carriers_is_active_filter(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    await _make_carrier(db_session, name="黑貓宅急便", slug="tcat")
    inactive = Carrier(name="停用商", slug="inactive1", kind=CarrierKind.other, is_active=False)
    db_session.add(inactive)
    await db_session.commit()

    resp = await client.get("/api/v1/carriers", params={"is_active": "true"})
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
