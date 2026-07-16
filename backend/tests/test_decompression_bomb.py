"""Decompression-bomb protection (M2-R1 blocking #2): app/security/image_ops.py
(upload-time re-encode) and app/ocr/image_prep.py (pre-AI-call compression)
both cap `Image.MAX_IMAGE_PIXELS` far below Pillow's own default and upgrade
`DecompressionBombWarning` to a hard error, so a hostile/malformed image
never gets decoded into hundreds of MB of raw pixel data.

Fixture images are built via `Image.new(...)` (which Pillow does *not*
pixel-bomb-check -- only the *decode* path, `Image.open()`/`.load()`, is
guarded) and saved as PNG, which compresses a solid-color canvas down to a
few hundred KB -- comfortably inside the 15MB per-file upload cap, and
critically: this test suite never actually allocates hundreds of MB of
memory to prove the guard works, it only proves decode-time rejection.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.models.enums import UserRole
from app.ocr.image_prep import prepare_for_ai
from app.security.image_ops import MAX_IMAGE_PIXELS, InvalidImageError, reencode_strip_exif
from tests._helpers import login_as


def _oversized_png_bytes() -> bytes:
    # 7000 * 7000 = 49,000,000 pixels > MAX_IMAGE_PIXELS (40,000,000).
    side = 7000
    assert side * side > MAX_IMAGE_PIXELS
    img = Image.new("RGB", (side, side), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    # Sanity: a solid-color PNG of this size compresses to well under the
    # 15MB per-file upload cap -- this is a "declares huge dimensions, tiny
    # on-disk size" bomb shape, not merely a large upload.
    assert len(data) < 1_000_000
    return data


def _small_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (60, 40), color=(120, 40, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_max_image_pixels_is_capped_well_below_pillows_default():
    # Pillow's own stock default is ~178,956,970 (~178MP) -- this must be
    # meaningfully lower (the task brief's "~40MP").
    assert MAX_IMAGE_PIXELS == 40_000_000
    assert Image.MAX_IMAGE_PIXELS == MAX_IMAGE_PIXELS


def test_reencode_strip_exif_rejects_oversized_image():
    with pytest.raises(InvalidImageError):
        reencode_strip_exif(_oversized_png_bytes(), "image/png")


def test_reencode_strip_exif_still_accepts_a_normal_photo():
    sanitized, width, height = reencode_strip_exif(_small_jpeg_bytes(), "image/jpeg")
    assert (width, height) == (60, 40)
    assert sanitized


def test_prepare_for_ai_rejects_oversized_image():
    with pytest.raises(InvalidImageError):
        prepare_for_ai(_oversized_png_bytes())


def test_prepare_for_ai_still_compresses_a_normal_photo():
    result = prepare_for_ai(_small_jpeg_bytes())
    assert result
    # Sanity check it's still a decodable JPEG (prepare_for_ai always
    # re-encodes to JPEG regardless of input format).
    out = Image.open(io.BytesIO(result))
    out.load()
    assert out.format == "JPEG"


async def test_upload_endpoint_rejects_decompression_bomb(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/uploads",
        files={"files": ("bomb.png", _oversized_png_bytes(), "image/png")},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "UPLOAD_BAD_TYPE"
