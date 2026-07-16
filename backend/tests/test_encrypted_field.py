import base64
import json
import os

import pytest
from sqlalchemy import text

from app.config import reset_settings_cache
from app.models.employee import Employee
from app.models.types import EncryptionKeyError, decrypt_value, encrypt_value


def test_encrypt_decrypt_roundtrip_pure():
    plaintext = "0912-345-678"
    ciphertext = encrypt_value(plaintext)

    assert ciphertext.startswith("k1:")
    assert ciphertext != plaintext
    assert decrypt_value(ciphertext) == plaintext


def test_decrypt_legacy_v1_prefix_still_works(monkeypatch):
    """Ciphertext written by the pre-rotation code used a `v1:` prefix tied
    to the single ENCRYPTION_KEY. That must keep decrypting after the
    key-registry rewrite (M0-R1 blocking #4)."""
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    monkeypatch.delenv("ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("ENCRYPTION_ACTIVE_KEY", raising=False)
    reset_settings_cache()

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(base64.b64decode(key))
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, b"legacy-secret", None)
    legacy_ciphertext = "v1:" + base64.b64encode(nonce + ct).decode()

    assert decrypt_value(legacy_ciphertext) == "legacy-secret"


def test_key_rotation_new_writes_use_active_version_old_reads_still_work(monkeypatch):
    """ENCRYPTION_KEYS + ENCRYPTION_ACTIVE_KEY: encrypting under k2 must not
    break decrypting data still tagged k1 (M0-R1 blocking #4 rotation)."""
    key1 = base64.b64encode(os.urandom(32)).decode()
    key2 = base64.b64encode(os.urandom(32)).decode()

    monkeypatch.setenv("ENCRYPTION_KEYS", json.dumps({"k1": key1, "k2": key2}))
    monkeypatch.setenv("ENCRYPTION_ACTIVE_KEY", "k1")
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    reset_settings_cache()

    old_ciphertext = encrypt_value("secret-under-k1")
    assert old_ciphertext.startswith("k1:")

    # Rotate: k2 becomes active.
    monkeypatch.setenv("ENCRYPTION_ACTIVE_KEY", "k2")
    reset_settings_cache()

    new_ciphertext = encrypt_value("secret-under-k2")
    assert new_ciphertext.startswith("k2:")

    # Both old (k1) and new (k2) ciphertext must still decrypt correctly.
    assert decrypt_value(old_ciphertext) == "secret-under-k1"
    assert decrypt_value(new_ciphertext) == "secret-under-k2"


def test_decrypt_unknown_key_version_raises(monkeypatch):
    key1 = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("ENCRYPTION_KEYS", json.dumps({"k1": key1}))
    monkeypatch.setenv("ENCRYPTION_ACTIVE_KEY", "k1")
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    reset_settings_cache()

    with pytest.raises(EncryptionKeyError):
        decrypt_value("k99:AAAAAAAAAAAAAAAAAAAA")


def test_production_rejects_non_32byte_key(monkeypatch):
    """M0-R1 blocking #5: production must not silently fold a weak key."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENCRYPTION_KEY", "not-a-valid-base64-32-byte-key")
    monkeypatch.setenv("SECRET_KEY", "irrelevant-for-this-test")
    reset_settings_cache()

    with pytest.raises(EncryptionKeyError):
        encrypt_value("anything")

    # Restore development so the autouse fixture's post-test reset is clean.
    monkeypatch.setenv("ENVIRONMENT", "development")
    reset_settings_cache()


def test_development_allows_weak_key_fallback(monkeypatch):
    """Development is allowed to fold an arbitrary string into a key (with a
    warning) so a throwaway local .env doesn't hard-crash."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ENCRYPTION_KEY", "just-a-dev-string")
    reset_settings_cache()

    ciphertext = encrypt_value("dev-secret")
    assert decrypt_value(ciphertext) == "dev-secret"


async def test_encrypted_field_roundtrip(db_session, db_engine):
    plaintext_email = "employee@example.com"
    plaintext_phone = "0987-654-321"

    employee = Employee(
        name="Wang", aliases=["Wang Xiaoming"], email=plaintext_email, phone=plaintext_phone
    )
    db_session.add(employee)
    await db_session.commit()
    employee_id = employee.id

    # Read back through the ORM: the TypeDecorator should transparently
    # decrypt the stored ciphertext.
    db_session.expire_all()
    reloaded = await db_session.get(Employee, employee_id)
    assert reloaded.email == plaintext_email
    assert reloaded.phone == plaintext_phone

    # Read the raw column value directly to prove it is *not* stored as
    # plaintext at rest.
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT email, phone FROM employees WHERE id = :id"), {"id": employee_id}
            )
        ).one()
    assert row.email != plaintext_email
    assert row.email.startswith("k1:")
    assert row.phone != plaintext_phone
    assert row.phone.startswith("k1:")


async def test_encrypted_field_nullable(db_session):
    employee = Employee(name="NoContact", aliases=[])
    db_session.add(employee)
    await db_session.commit()
    employee_id = employee.id
    db_session.expire_all()

    reloaded = await db_session.get(Employee, employee_id)
    assert reloaded.email is None
