"""Application-layer field encryption.

`Encrypted` is a SQLAlchemy TypeDecorator that transparently encrypts a
string column with AES-256-GCM before it hits the database, and decrypts it
on the way out. Ciphertext is stored as `k<version>:<base64(nonce +
ciphertext)>` per docs/plan/07-SECURITY.md section 3 (M0-R1 blocking #4: the
version prefix is what makes key rotation possible -- old rows keep
decrypting with the key version they were written under while new rows use
the current active key).

Key handling / sources (in order of precedence):

- `ENCRYPTION_KEYS`: JSON object mapping a key version label to a
  base64-encoded 32-byte key, e.g. `{"k1": "<base64>", "k2": "<base64>"}`.
  `ENCRYPTION_ACTIVE_KEY` picks which of those versions new ciphertext is
  written with (e.g. `"k2"`). This is the rotation-capable form.
- `ENCRYPTION_KEY`: legacy single-key form. Registered as both `"k1"` (so a
  deployment that has never rotated keys just keeps working with the `k1:`
  prefix) and `"v1"` (so ciphertext written by the *pre-rotation* code,
  which used the `v1:` prefix, still decrypts -- M0-R1 blocking #4
  "backward compatible v1: prefix reads").

Key strength (M0-R1 blocking #5): each configured key must be a
base64-encoded 32-byte value. In production, a key that fails that check is
a hard startup error -- we refuse to silently run with a weakly-derived
key. In development, a non-conforming key is folded into 32 bytes via
SHA-256 as a convenience fallback, with a warning logged, so a throwaway
`.env` with e.g. `ENCRYPTION_KEY=dev` doesn't hard-crash local development.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy.types import String, TypeDecorator

from app.config import get_settings

logger = logging.getLogger(__name__)


def sa_enum(enum_cls: type[enum.Enum], name: str | None = None) -> SAEnum:
    """A portable (non-native) string-backed SQLAlchemy Enum column type.

    Storing as plain VARCHAR + CHECK (native_enum=False) keeps SQLite and
    PostgreSQL schemas identical and avoids Postgres `ALTER TYPE ... ADD
    VALUE` migrations whenever we add an enum member.
    """
    return SAEnum(
        enum_cls,
        name=name or enum_cls.__name__.lower(),
        native_enum=False,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class UtcDateTime(TypeDecorator):
    """A timezone-correct DateTime column.

    `DateTime(timezone=True)` is a *lie on SQLite*: the driver has nowhere to
    put an offset, so it silently drops tzinfo. That broke both directions --

      write: an aware `14:30:05+08:00` from an API client was stored as the
             bare wall clock `14:30:05` and thereafter read as if it were
             UTC, i.e. 8 hours wrong in the database;
      read:  a UTC value came back *naive*, so `datetime.isoformat()` emitted
             `"2026-07-16T06:30:05"` with no offset. JS parses an offset-less
             date-time as **local** time, so the UI rendered every timestamp
             8 hours early for a Taipei browser.

    This decorator makes "aware UTC in, aware UTC out" true on every dialect:
    bind normalizes to UTC (naive input is taken as UTC, which is what all
    server-side `datetime.now(timezone.utc)` values already are), and result
    re-attaches UTC to whatever the driver hands back. Postgres, which does
    store the offset, is unaffected -- the values simply pass through already
    normalized.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


_LEGACY_PREFIX = "v1"
_DEFAULT_ACTIVE_VERSION = "k1"


class EncryptionKeyError(RuntimeError):
    """Raised when the configured encryption key material is invalid."""


def _decode_strict_32(raw: str) -> bytes | None:
    """Return 32 raw bytes if `raw` is valid base64 encoding exactly that, else None."""
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        return None
    return decoded if len(decoded) == 32 else None


def _resolve_key(raw: str, *, label: str, is_production: bool) -> bytes:
    """Turn a configured key string into 32 raw key bytes.

    Production: the key MUST be valid base64 for exactly 32 bytes, or we
    raise (M0-R1 blocking #5 -- no silent weak-key fallback in prod).
    Development: fall back to a SHA-256 fold of the raw string, with a
    warning, so ad-hoc dev secrets don't hard-crash the app.
    """
    strict = _decode_strict_32(raw)
    if strict is not None:
        return strict

    if is_production:
        raise EncryptionKeyError(
            f"Encryption key '{label}' is not a valid base64-encoded 32-byte key. "
            "Generate one with `openssl rand -base64 32`. Refusing to start in "
            "production with a weak/derived key (see docs/plan/07-SECURITY.md section 3)."
        )

    logger.warning(
        "Encryption key '%s' is not a valid base64 32-byte value; falling back to a "
        "SHA-256-derived key. This is a development-only convenience and MUST NOT be "
        "relied on in production.",
        label,
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _build_key_registry() -> tuple[dict[str, bytes], str]:
    """Return (version_label -> 32 raw key bytes, active_version_label)."""
    settings = get_settings()
    is_production = settings.is_production

    registry: dict[str, bytes] = {}

    if settings.encryption_keys:
        try:
            parsed = json.loads(settings.encryption_keys)
        except (json.JSONDecodeError, TypeError) as exc:
            raise EncryptionKeyError(
                "ENCRYPTION_KEYS is not valid JSON. Expected an object like "
                '{"k1": "<base64 32-byte key>"}.'
            ) from exc
        if not isinstance(parsed, dict) or not parsed:
            raise EncryptionKeyError(
                "ENCRYPTION_KEYS must be a non-empty JSON object of "
                'version-label -> base64 key, e.g. {"k1": "<base64>"}.'
            )
        for label, raw in parsed.items():
            registry[label] = _resolve_key(str(raw), label=label, is_production=is_production)

    if settings.encryption_key:
        legacy_bytes = _resolve_key(
            settings.encryption_key, label="ENCRYPTION_KEY", is_production=is_production
        )
        # Backward compatibility: ciphertext written before key-rotation
        # support used the "v1:" prefix and this single key.
        registry.setdefault(_LEGACY_PREFIX, legacy_bytes)
        # A deployment that has never configured ENCRYPTION_KEYS keeps using
        # this same key as version "k1" going forward.
        registry.setdefault(_DEFAULT_ACTIVE_VERSION, legacy_bytes)

    if not registry:
        raise EncryptionKeyError(
            "No encryption key configured. Set ENCRYPTION_KEY (single key) or "
            "ENCRYPTION_KEYS + ENCRYPTION_ACTIVE_KEY (rotation-capable)."
        )

    active_version = settings.encryption_active_key or _DEFAULT_ACTIVE_VERSION
    if active_version not in registry:
        raise EncryptionKeyError(
            f"ENCRYPTION_ACTIVE_KEY '{active_version}' is not present in the "
            "configured key set."
        )

    return registry, active_version


def _key_bytes_for(version: str) -> bytes:
    registry, _active = _build_key_registry()
    try:
        return registry[version]
    except KeyError as exc:
        raise EncryptionKeyError(
            f"No encryption key registered for version '{version}'. Ciphertext "
            "written under a rotated-out key cannot be decrypted without it."
        ) from exc


def _active_key() -> tuple[str, bytes]:
    registry, active_version = _build_key_registry()
    return active_version, registry[active_version]


def validate_encryption_keys_or_raise() -> None:
    """Eagerly validate encryption key configuration (call at app startup).

    Building the registry already performs the production strength check
    (M0-R1 blocking #5); calling this from `create_app()` means a
    misconfigured production deployment fails fast at boot instead of on
    the first encrypted write.
    """
    _build_key_registry()


def encrypt_value(plaintext: str, *, aad: str | None = None) -> str:
    version, key = _active_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    associated_data = aad.encode("utf-8") if aad else None
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data)
    return f"{version}:" + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_value(ciphertext: str, *, aad: str | None = None) -> str:
    if ":" not in ciphertext:
        raise ValueError("Unsupported or missing ciphertext version prefix")
    version, _, encoded = ciphertext.partition(":")
    key = _key_bytes_for(version)
    raw = base64.b64decode(encoded)
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    associated_data = aad.encode("utf-8") if aad else None
    return aesgcm.decrypt(nonce, ct, associated_data).decode("utf-8")


def encrypt_bytes(plaintext: bytes, *, aad: str | None = None) -> bytes:
    """Byte-oriented sibling of `encrypt_value`, for encrypting file contents
    (e.g. pickup signature PNGs) before they are written to UPLOAD_DIR --
    same AES-256-GCM key registry / rotation scheme as encrypted DB columns
    (07-SECURITY.md section 3), just applied to a file instead of a column.
    Format on disk: b"<version>:" + nonce(12) + ciphertext.
    """
    version, key = _active_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    associated_data = aad.encode("utf-8") if aad else None
    ct = aesgcm.encrypt(nonce, plaintext, associated_data)
    return f"{version}:".encode("ascii") + nonce + ct


def decrypt_bytes(blob: bytes, *, aad: str | None = None) -> bytes:
    prefix, sep, rest = blob.partition(b":")
    if not sep:
        raise ValueError("Unsupported or missing ciphertext version prefix")
    version = prefix.decode("ascii")
    key = _key_bytes_for(version)
    nonce, ct = rest[:12], rest[12:]
    aesgcm = AESGCM(key)
    associated_data = aad.encode("utf-8") if aad else None
    return aesgcm.decrypt(nonce, ct, associated_data)


class Encrypted(TypeDecorator):
    """A String column that is AES-256-GCM encrypted at rest.

    `aad` binds the ciphertext to a fixed "table.column" identity (AES-GCM
    additional authenticated data), so swapping ciphertext between columns
    can't succeed even with the right key. Ideally this would also bind the
    row id, but `TypeDecorator.process_bind_param`/`process_result_value`
    only see the raw column value -- SQLAlchemy does not hand the owning
    row/mapped object to a TypeDecorator at bind time, so a per-row id isn't
    available here. We fall back to "table.column" scoping and record this
    as a deliberate trade-off (see docs/reviews/M0-R1.md).
    """

    impl = String
    cache_ok = True

    def __init__(self, *args, aad: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._aad = aad

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return encrypt_value(value, aad=self._aad)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return decrypt_value(value, aad=self._aad)
