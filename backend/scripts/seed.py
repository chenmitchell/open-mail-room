"""Seed script: seeds the Taiwan carrier list, and (opt-in only) an admin user.

Usage (run against an already-migrated database, i.e. after
`alembic upgrade head`):

    python3 scripts/seed.py

SETUP-WIZARD: this script no longer creates an admin account by default.
The normal way to get the first administrator is the in-app first-run
wizard at `/setup` (backend: app/api/v1/setup.py's `GET /api/v1/setup/status`
+ `POST /api/v1/setup`) -- open the site once with zero admins in the
database and it walks you through choosing your own email/display
name/password, then locks itself. That replaces the old behavior of
auto-generating a random password and printing it once to the deploy log
(easy to miss, and a log stream isn't always something operators tightly
control access to).

Admin auto-creation here is now strictly opt-in, for automation/tests that
need a deterministic account without driving the UI: it only runs when
*both* ADMIN_EMAIL and ADMIN_PASSWORD are set in the environment (or
`.env`). If either is missing, admin seeding is skipped entirely and the
`/setup` wizard remains the way to create the first admin.

Idempotent: re-running only fills in what's missing (an existing admin
user / carriers are left untouched).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make `app` importable when this script is run directly, e.g.
# `python3 scripts/seed.py` from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_sessionmaker  # noqa: E402
from app.models.carrier import Carrier  # noqa: E402
from app.models.enums import CarrierKind, UserRole  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402

# Source: docs/plan/10-RESEARCH.md §3 (台灣收發通路與單號格式).
CARRIER_SEED: list[dict] = [
    {
        "name": "中華郵政掛號/包裹",
        "slug": "chunghwa_post",
        "kind": CarrierKind.postal,
        # 國內掛號/包裹號碼:舊式 14 碼(6 碼掛號號+6 碼收寄局碼+2 碼類別碼),
        # 新式 20 碼(14 碼再加 6 碼寄達地郵遞區號,A7 分揀機規格)。
        "tracking_pattern": r"^(\d{14}|\d{20})$",
    },
    {
        "name": "中華郵政快捷 EMS",
        "slug": "chunghwa_post_ems",
        "kind": CarrierKind.postal,
        "tracking_pattern": r"^[A-Z]{2}\d{9}TW$",
    },
    {
        "name": "中華郵政 i郵箱",
        "slug": "chunghwa_post_ibox",
        "kind": CarrierKind.postal,
        "tracking_pattern": None,
    },
    {
        "name": "黑貓宅急便",
        "slug": "tcat",
        "kind": CarrierKind.courier,
        "tracking_pattern": r"^\d{12}$",
    },
    {
        "name": "新竹物流",
        "slug": "hct",
        "kind": CarrierKind.courier,
        "tracking_pattern": r"^\d{10}$",
    },
    {
        "name": "嘉里大榮",
        "slug": "kerrytj",
        "kind": CarrierKind.freight,
        "tracking_pattern": r"^\d{10,11}$",
    },
    {
        "name": "台灣宅配通",
        "slug": "ecan",
        "kind": CarrierKind.courier,
        "tracking_pattern": r"^\d{12}",
    },
    {
        "name": "順豐速運",
        "slug": "sf",
        "kind": CarrierKind.courier,
        "tracking_pattern": r"^SF\d{12,15}$",
    },
    {
        "name": "DHL Express",
        "slug": "dhl",
        "kind": CarrierKind.courier,
        "tracking_pattern": r"^\d{10}$",
    },
    {
        "name": "FedEx",
        "slug": "fedex",
        "kind": CarrierKind.courier,
        "tracking_pattern": r"^\d{12,14}$",
    },
    {
        "name": "UPS",
        "slug": "ups",
        "kind": CarrierKind.courier,
        "tracking_pattern": r"^1Z[0-9A-Z]{16}$",
    },
    {
        "name": "7-11 交貨便",
        "slug": "seven_eleven",
        "kind": CarrierKind.store,
        "tracking_pattern": r"^G\d{10}$",
    },
    {
        "name": "全家店到店",
        "slug": "familymart",
        "kind": CarrierKind.store,
        "tracking_pattern": None,
    },
    {
        "name": "機車快遞",
        "slug": "messenger",
        "kind": CarrierKind.messenger,
        "tracking_pattern": None,
    },
    {
        "name": "PChome 網家速配",
        "slug": "pchome",
        "kind": CarrierKind.courier,
        "tracking_pattern": None,
    },
    {
        "name": "momo",
        "slug": "momo",
        "kind": CarrierKind.courier,
        "tracking_pattern": None,
    },
    {
        "name": "酷澎 Coupang",
        "slug": "coupang",
        "kind": CarrierKind.courier,
        "tracking_pattern": None,
    },
    {
        "name": "專人親送",
        "slug": "personal_delivery",
        "kind": CarrierKind.other,
        "tracking_pattern": None,
    },
    {
        "name": "其他",
        "slug": "other",
        "kind": CarrierKind.other,
        "tracking_pattern": None,
    },
]


async def seed_carriers(session) -> int:
    result = await session.execute(select(Carrier.slug))
    existing_slugs = {row[0] for row in result.all()}

    created = 0
    for entry in CARRIER_SEED:
        if entry["slug"] in existing_slugs:
            continue
        session.add(
            Carrier(
                name=entry["name"],
                slug=entry["slug"],
                kind=entry["kind"],
                tracking_pattern=entry["tracking_pattern"],
                is_active=True,
            )
        )
        created += 1
    if created:
        await session.commit()
    return created


async def seed_admin(session) -> bool:
    """Opt-in admin auto-creation. Returns whether an admin was created.

    SETUP-WIZARD: only runs when *both* ADMIN_EMAIL and ADMIN_PASSWORD are
    set (via app.config.Settings, which supports `.env` same as every other
    setting in this app -- RC-FIX #8's original point). If either is blank,
    this is a no-op: the humans-first-run path is the `/api/v1/setup`
    wizard, not an env-var-triggered auto-create. No password is ever
    generated or printed here anymore.
    """
    settings = get_settings()
    admin_email = (settings.admin_email or "").strip().lower()
    admin_password = settings.admin_password or ""

    if not admin_email or not admin_password:
        return False

    result = await session.execute(select(User).where(User.email == admin_email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return False

    user = User(
        email=admin_email,
        password_hash=hash_password(admin_password),
        display_name="Administrator",
        role=UserRole.admin,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    return True


async def main() -> None:
    settings = get_settings()
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        admin_created = await seed_admin(session)
        carriers_created = await seed_carriers(session)

    if admin_created:
        seeded_email = (settings.admin_email or "").strip().lower()
        print(f"Created admin user: {seeded_email}")
    elif settings.admin_email or settings.admin_password:
        print(
            "ADMIN_EMAIL/ADMIN_PASSWORD were only partially set, or an admin "
            "already exists -- skipped auto-creating an admin."
        )
    else:
        print(
            "No ADMIN_EMAIL/ADMIN_PASSWORD provided -- skipping admin "
            "auto-creation. Open the site and visit /setup to create the "
            "first administrator."
        )

    print(f"Seeded {carriers_created} new carrier(s) (of {len(CARRIER_SEED)} total).")


if __name__ == "__main__":
    asyncio.run(main())
