"""POST/GET /uploads (03-API-SPEC.md section 2, 07-SECURITY.md section 4):
magic-byte validation, batch/per-file size caps, EXIF stripping,
encryption-at-rest, and read-back authorization (pending/confidential
photos restricted to admin/counter).
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

from app.models.attachment import Attachment
from app.models.enums import AttachmentKind, AttachmentOwnerType, MailStatus, MailType, UserRole
from app.models.mail_item import MailItem
from app.security.file_crypto import read_encrypted_file, save_encrypted_file
from tests._helpers import login_as


def _jpeg_bytes(size=(60, 40), *, exif=None) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", size, color=(120, 40, 200))
    kwargs = {}
    if exif is not None:
        kwargs["exif"] = exif
    img.save(buf, format="JPEG", **kwargs)
    return buf.getvalue()


def _jpeg_with_orientation(width: int, height: int, orientation: int) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(10, 200, 30))
    exif = Image.Exif()
    exif[0x0112] = orientation  # Orientation tag
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _png_bytes(size=(10, 10)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", size, color=(0, 255, 0, 128)).save(buf, format="PNG")
    return buf.getvalue()


def _webp_bytes(size=(10, 10)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=(255, 0, 0)).save(buf, format="WEBP")
    return buf.getvalue()


async def test_upload_requires_counter_or_admin(client, db_session):
    await login_as(client, db_session, role=UserRole.employee)
    resp = await client.post(
        "/api/v1/uploads", files={"files": ("a.jpg", _jpeg_bytes(), "image/jpeg")}
    )
    assert resp.status_code == 403


async def test_upload_unauthenticated_rejected(client):
    resp = await client.post(
        "/api/v1/uploads", files={"files": ("a.jpg", _jpeg_bytes(), "image/jpeg")}
    )
    # No session cookie at all means no CSRF cookie either -- the
    # router-level CSRF dependency (checked before the route's own
    # require_role) rejects first, same as every other write endpoint in
    # this app (see tests/test_csrf.py).
    assert resp.status_code == 403


async def test_upload_accepts_jpeg_png_webp(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    for filename, data, mime in [
        ("a.jpg", _jpeg_bytes(), "image/jpeg"),
        ("b.png", _png_bytes(), "image/png"),
        ("c.webp", _webp_bytes(), "image/webp"),
    ]:
        resp = await client.post("/api/v1/uploads", files={"files": (filename, data, mime)})
        assert resp.status_code == 201, resp.text
        att = resp.json()["data"]["attachments"][0]
        assert att["mime"] == mime
        assert att["size_bytes"] > 0
        assert att["width"] and att["height"]


async def test_upload_rejects_bad_magic_bytes_despite_correct_content_type(client, db_session):
    """07-SECURITY.md section 4: never trust filename/Content-Type -- a
    text file relabeled as image/jpeg must still be rejected."""
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/uploads",
        files={"files": ("fake.jpg", b"this is not an image at all", "image/jpeg")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UPLOAD_BAD_TYPE"


async def test_upload_rejects_disallowed_mime_svg(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    resp = await client.post("/api/v1/uploads", files={"files": ("x.svg", svg, "image/svg+xml")})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UPLOAD_BAD_TYPE"


async def test_upload_rejects_batch_over_limit(client, db_session, monkeypatch):
    await login_as(client, db_session, role=UserRole.admin)
    monkeypatch.setattr("app.api.v1.uploads.MAX_UPLOAD_FILES", 2)

    files = [("files", (f"{i}.jpg", _jpeg_bytes(), "image/jpeg")) for i in range(3)]
    resp = await client.post("/api/v1/uploads", files=files)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


async def test_upload_rejects_oversized_single_file(client, db_session, monkeypatch):
    await login_as(client, db_session, role=UserRole.admin)
    monkeypatch.setattr("app.api.v1.uploads.MAX_UPLOAD_FILE_BYTES", 100)

    big = _jpeg_bytes(size=(200, 200))
    assert len(big) > 100
    resp = await client.post("/api/v1/uploads", files={"files": ("big.jpg", big, "image/jpeg")})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


async def test_upload_strips_exif_and_bakes_orientation(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)

    original = _jpeg_with_orientation(40, 20, orientation=6)  # 90deg CW
    assert b"Exif" in original  # sanity: the fixture really has EXIF

    resp = await client.post(
        "/api/v1/uploads", files={"files": ("oriented.jpg", original, "image/jpeg")}
    )
    assert resp.status_code == 201, resp.text
    att = resp.json()["data"]["attachments"][0]

    # Orientation 6 (rotate 90 CW) baked in: a 40x20 source becomes 20x40.
    assert (att["width"], att["height"]) == (20, 40)

    get_resp = await client.get(f"/api/v1/uploads/{att['id']}")
    assert get_resp.status_code == 200
    assert b"Exif" not in get_resp.content


async def test_upload_encrypted_at_rest(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)

    plaintext_ish = _jpeg_bytes()
    resp = await client.post(
        "/api/v1/uploads", files={"files": ("a.jpg", plaintext_ish, "image/jpeg")}
    )
    assert resp.status_code == 201, resp.text
    attachment_id = resp.json()["data"]["attachments"][0]["id"]

    db_session.expire_all()
    attachment = await db_session.get(Attachment, attachment_id)
    assert attachment is not None

    from pathlib import Path

    from app.config import get_settings

    raw_on_disk = (Path(get_settings().upload_dir) / attachment.file_path).read_bytes()
    # AES-256-GCM ciphertext: never contains the plaintext JPEG magic bytes,
    # and starts with the key-version prefix (app.models.types format).
    assert b"\xff\xd8\xff" not in raw_on_disk[:16]
    assert raw_on_disk.startswith(b"k1:")

    decrypted = read_encrypted_file(attachment.file_path)
    assert decrypted.startswith(b"\xff\xd8\xff")


async def test_get_upload_not_found(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.get("/api/v1/uploads/does-not-exist")
    assert resp.status_code == 404


async def test_get_pending_upload_restricted_to_admin_counter(client, db_session):
    await login_as(client, db_session, role=UserRole.admin)
    resp = await client.post(
        "/api/v1/uploads", files={"files": ("a.jpg", _jpeg_bytes(), "image/jpeg")}
    )
    attachment_id = resp.json()["data"]["attachments"][0]["id"]

    from tests._helpers import create_user, login

    await create_user(db_session, email="viewer1@example.com", role=UserRole.viewer)
    await login(client, email="viewer1@example.com")

    resp = await client.get(f"/api/v1/uploads/{attachment_id}")
    assert resp.status_code == 403


async def test_get_upload_linked_to_confidential_item_restricted(client, db_session):
    admin = await login_as(client, db_session, role=UserRole.admin)

    item = MailItem(
        item_no="IN-20260711-0001",
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

    stored = save_encrypted_file(_jpeg_bytes(), subdir="mail_photos/pending", extension="jpg")
    attachment = Attachment(
        owner_type=AttachmentOwnerType.mail_item,
        owner_id=item.id,
        kind=AttachmentKind.label_photo,
        file_path=stored["file_path"],
        sha256=stored["sha256"],
        mime="image/jpeg",
        size_bytes=stored["size_bytes"],
        width=60,
        height=40,
    )
    db_session.add(attachment)
    await db_session.commit()
    await db_session.refresh(attachment)

    from tests._helpers import create_user, login

    await create_user(db_session, email="viewer2@example.com", role=UserRole.viewer)
    await login(client, email="viewer2@example.com")
    resp = await client.get(f"/api/v1/uploads/{attachment.id}")
    assert resp.status_code == 403

    # Log back in as admin -- allowed, and the underlying file genuinely
    # decrypts back to the original JPEG.
    await login(client, email=admin.email)
    resp2 = await client.get(f"/api/v1/uploads/{attachment.id}")
    assert resp2.status_code == 200
    assert resp2.content.startswith(b"\xff\xd8\xff")
