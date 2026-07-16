"""Typed helpers over the generic `settings` key-value table for the
notification subsystem.

`app/models/setting.py` documents a known gap: `value_json` is plain JSON,
not encrypted, even though 07-SECURITY.md section 3 lists secrets that must
be encrypted at rest. The task brief for M3-01 explicitly calls this out for
channel tokens ("channel token 加密存 settings"), so this module closes that
gap *at the call site* for the specific keys that hold secrets: on write, the
plaintext string is AES-256-GCM encrypted with `app.models.types.encrypt_value`
(same key registry as every other `Encrypted` column) before being stored in
`value_json`; on read it's decrypted back. Non-secret settings (templates,
day thresholds, strategy) are stored as plain JSON as before.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import Setting
from app.models.types import decrypt_value, encrypt_value

_SECRET_AAD = "settings.value_json.secret"


async def get_setting(session: AsyncSession, key: str, *, default: Any = None) -> Any:
    row = (await session.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row is None:
        return default
    if row.is_secret:
        if row.value_json is None:
            return default
        try:
            return decrypt_value(str(row.value_json), aad=_SECRET_AAD)
        except Exception:  # noqa: BLE001 - a corrupt/foreign-key-version value degrades to "unset"
            return default
    return row.value_json if row.value_json is not None else default


async def set_setting(
    session: AsyncSession, key: str, value: Any, *, secret: bool = False
) -> Setting:
    row = (await session.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    stored = encrypt_value(str(value), aad=_SECRET_AAD) if secret else value
    if row is None:
        row = Setting(key=key, value_json=stored, is_secret=secret)
        session.add(row)
    else:
        row.value_json = stored
        row.is_secret = secret
    await session.flush()
    return row


async def get_int_setting(session: AsyncSession, key: str, *, default: int) -> int:
    value = await get_setting(session, key, default=default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def get_bool_setting(session: AsyncSession, key: str, *, default: bool) -> bool:
    value = await get_setting(session, key, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value) if value is not None else default


async def get_dict_setting(session: AsyncSession, key: str) -> dict:
    value = await get_setting(session, key, default=None)
    return value if isinstance(value, dict) else {}
