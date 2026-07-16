from scripts.seed import CARRIER_SEED, seed_carriers
from sqlalchemy import func, select

from app.models.carrier import Carrier


async def test_seed_carriers_creates_all(db_session):
    created = await seed_carriers(db_session)
    assert created == len(CARRIER_SEED)

    result = await db_session.execute(select(func.count()).select_from(Carrier))
    assert result.scalar_one() == len(CARRIER_SEED)

    result = await db_session.execute(select(Carrier.slug))
    slugs = {row[0] for row in result.all()}
    expected_slugs = {entry["slug"] for entry in CARRIER_SEED}
    assert slugs == expected_slugs

    # A couple of spot checks against docs/plan/10-RESEARCH.md §3.
    result = await db_session.execute(select(Carrier).where(Carrier.slug == "tcat"))
    tcat = result.scalar_one()
    assert tcat.name == "黑貓宅急便"
    assert tcat.tracking_pattern == r"^\d{12}$"

    result = await db_session.execute(select(Carrier).where(Carrier.slug == "ups"))
    ups = result.scalar_one()
    assert ups.tracking_pattern == r"^1Z[0-9A-Z]{16}$"


async def test_seed_carriers_idempotent(db_session):
    first_run = await seed_carriers(db_session)
    assert first_run == len(CARRIER_SEED)

    second_run = await seed_carriers(db_session)
    assert second_run == 0

    result = await db_session.execute(select(func.count()).select_from(Carrier))
    assert result.scalar_one() == len(CARRIER_SEED)
