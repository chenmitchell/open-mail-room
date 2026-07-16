"""EXIF capture-time extraction (app/security/image_ops.extract_capture_time)
and its exposure through POST /uploads.

The EXIF block is destroyed at intake on purpose (GPS is personal data --
07-SECURITY.md section 4). The capture timestamp is the one field lifted out
*before* that strip, because "when was this actually photographed?" can differ
from `received_at` when photos are uploaded in a later batch. These tests pin
both halves: that we read it correctly, and that we still throw the rest away.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

from app.models.enums import UserRole
from app.security.image_ops import extract_capture_time, reencode_strip_exif
from tests._helpers import login_as


def _jpeg_with_exif(
    tags: dict[int, object] | None = None,
    sub: dict[int, object] | None = None,
) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (24, 16), color=(200, 30, 60))
    exif = Image.Exif()
    for k, v in (tags or {}).items():
        exif[k] = v
    if sub:
        ifd = exif.get_ifd(0x8769)
        for k, v in sub.items():
            ifd[k] = v
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _plain_jpeg() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (12, 8), color=(1, 2, 3)).save(buf, format="JPEG")
    return buf.getvalue()


# --- unit: extract_capture_time ---------------------------------------


def test_capture_time_no_exif_returns_none():
    """A screenshot / re-saved image has no EXIF at all. That is a normal
    upload, not an error -- it just has no capture time."""
    assert extract_capture_time(_plain_jpeg(), "image/jpeg") is None


def test_capture_time_datetime_original_assumed_taipei():
    """No OffsetTime tag (the common case on real phones): the wall clock is
    read as Taiwan time and normalized to UTC."""
    data = _jpeg_with_exif(sub={36867: "2026:07:16 14:30:05"})
    got = extract_capture_time(data, "image/jpeg")
    assert got == datetime(2026, 7, 16, 6, 30, 5, tzinfo=timezone.utc)


def test_capture_time_honors_explicit_offset():
    """When the camera *did* record an offset, that wins over the +08:00
    assumption -- a photo taken abroad must not be shifted into Taipei."""
    data = _jpeg_with_exif(sub={36867: "2026:07:16 14:30:05", 36881: "-05:00"})
    got = extract_capture_time(data, "image/jpeg")
    assert got == datetime(2026, 7, 16, 19, 30, 5, tzinfo=timezone.utc)


def test_capture_time_falls_back_to_digitized_then_base_datetime():
    digitized = _jpeg_with_exif(sub={36868: "2026:07:16 08:00:00"})
    assert extract_capture_time(digitized, "image/jpeg") == datetime(
        2026, 7, 16, 0, 0, 0, tzinfo=timezone.utc
    )
    base = _jpeg_with_exif(tags={306: "2026:07:16 09:00:00"})
    assert extract_capture_time(base, "image/jpeg") == datetime(
        2026, 7, 16, 1, 0, 0, tzinfo=timezone.utc
    )


def test_capture_time_dead_camera_clock_dropped():
    """A camera with a dead coin cell writes its epoch default. Showing
    "拍攝於 1970" is worse than showing nothing."""
    data = _jpeg_with_exif(sub={36867: "1970:01:01 00:00:00"})
    assert extract_capture_time(data, "image/jpeg") is None


def test_capture_time_future_stamp_dropped():
    future = datetime.now(timezone.utc) + timedelta(days=30)
    data = _jpeg_with_exif(sub={36867: future.strftime("%Y:%m:%d %H:%M:%S")})
    assert extract_capture_time(data, "image/jpeg") is None


def test_capture_time_garbage_values_never_raise():
    for value in ("not a date", "", "2026-07-16 14:30:05", "\x00\x00"):
        assert extract_capture_time(_jpeg_with_exif(sub={36867: value}), "image/jpeg") is None
    assert extract_capture_time(b"not an image at all", "image/jpeg") is None
    assert extract_capture_time(_plain_jpeg(), "application/pdf") is None


def test_capture_time_bad_offset_falls_back_to_assumed_tz():
    data = _jpeg_with_exif(sub={36867: "2026:07:16 14:30:05", 36881: "banana"})
    assert extract_capture_time(data, "image/jpeg") == datetime(
        2026, 7, 16, 6, 30, 5, tzinfo=timezone.utc
    )


def test_exif_is_still_stripped_after_extraction():
    """Regression guard: reading the timestamp must not quietly turn into
    "keep the EXIF". GPS coordinates are personal data (07-SECURITY.md
    section 4) and must not survive intake even though we now read a
    neighbouring tag out of the same block."""
    from PIL import Image

    img = Image.new("RGB", (24, 16), color=(200, 30, 60))
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = "2026:07:16 14:30:05"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (25.0, 2.0, 0.0)  # 台北
    gps[3], gps[4] = "E", (121.0, 33.0, 0.0)
    exif[271] = "TestCam"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    data = buf.getvalue()

    # Precondition: the fixture really does carry GPS + capture time.
    assert Image.open(io.BytesIO(data)).getexif().get_ifd(0x8825)
    assert extract_capture_time(data, "image/jpeg") == datetime(
        2026, 7, 16, 6, 30, 5, tzinfo=timezone.utc
    )

    sanitized, _, _ = reencode_strip_exif(data, "image/jpeg")
    stored_exif = Image.open(io.BytesIO(sanitized)).getexif()
    assert not stored_exif
    assert not stored_exif.get_ifd(0x8825)


# --- integration: POST /uploads ---------------------------------------


async def test_upload_records_and_returns_capture_time(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    data = _jpeg_with_exif(sub={36867: "2026:07:16 14:30:05", 36881: "+08:00"})
    resp = await client.post("/api/v1/uploads", files={"files": ("phone.jpg", data, "image/jpeg")})
    assert resp.status_code == 201
    attachment = resp.json()["data"]["attachments"][0]
    assert attachment["captured_at"] == "2026-07-16T06:30:05+00:00"


async def test_upload_without_exif_reports_null_capture_time(client, db_session):
    await login_as(client, db_session, role=UserRole.counter)
    resp = await client.post(
        "/api/v1/uploads", files={"files": ("scan.jpg", _plain_jpeg(), "image/jpeg")}
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["attachments"][0]["captured_at"] is None
