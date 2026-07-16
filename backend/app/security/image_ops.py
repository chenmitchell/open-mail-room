"""Upload-time image validation and sanitization (07-SECURITY.md section 4):

    "僅允許 image/jpeg、image/png、image/webp、image/heic;魔數(magic bytes)
    驗證,不信任副檔名與 Content-Type。單檔 ≤15MB、單批 ≤30 張;以 Pillow
    重新編碼(去 EXIF -- EXIF 有 GPS 位置屬個資,同時消毒潛在惡意 payload)。"

HEIC/HEIF (iPhone's default, and some Android cameras) is now supported via
the optional `pillow-heif` dependency: a real phone camera going through the
`<input type=file capture>` fallback can hand us a `.heic` the browser itself
cannot even render (so the preview showed as a broken image and, worse, stock
Pillow couldn't decode it either -- OCR failed at image-prep). We register the
HEIF opener and *transcode HEIC to JPEG at intake*, so everything downstream
(storage, `GET /uploads/{id}`, the AI-facing copy) only ever deals with a
browser-renderable, Pillow-native JPEG. jpeg/png/webp are stored as-is.
"""

from __future__ import annotations

import io
import re
import warnings
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageFile, ImageOps

try:  # HEIF/HEIC support is best-effort: if the native lib is unavailable the
    # rest of the module still works for jpeg/png/webp exactly as before.
    from pillow_heif import register_heif_opener

    register_heif_opener()
    _HEIF_AVAILABLE = True
except Exception:  # noqa: BLE001 - missing/broken native lib -> HEIC just stays unsupported
    _HEIF_AVAILABLE = False

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# The save/output format per *input* mime. HEIC is decoded but re-encoded to
# JPEG (there is no browser that renders image/heic in an <img>, and JPEG is
# the right archival + AI-input format here), so its output mime is jpeg.
_FORMAT_BY_MIME = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/heic": "JPEG",
}
_OUTPUT_MIME = {
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
    "image/heic": "image/jpeg",
}
_EXT_BY_MIME = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

# Only the mimes we can actually decode are "allowed"; heic is conditional on
# the native lib having registered successfully.
ALLOWED_MIME_TYPES = frozenset(
    m for m in _FORMAT_BY_MIME if m != "image/heic" or _HEIF_AVAILABLE
)

# M2-R1 blocking #2: Pillow's own default `Image.MAX_IMAGE_PIXELS` (~178MP)
# only *warns* (DecompressionBombWarning) below 2x that ceiling and doesn't
# raise until ~356MP -- a well-crafted ~15MB (the per-file upload cap) PNG
# can still decode to hundreds of MB of raw pixel data before that ceiling is
# ever hit, and a 30-photo batch multiplies that. Capped to ~40MP here (well
# above any real phone-camera photo, e.g. a 48MP camera is already an
# outlier) and the "just warn" zone below the hard ceiling is upgraded to a
# hard error too, so nothing between "normal photo" and "the 356MP default
# ceiling" silently sails through as a warning-only log line.
MAX_IMAGE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
warnings.simplefilter("error", Image.DecompressionBombWarning)
# A truncated/partial image (e.g. a batch upload cut off mid-transfer that
# still passed magic-byte sniffing) must fail cleanly via InvalidImageError,
# not silently decode a corrupted partial frame.
ImageFile.LOAD_TRUNCATED_IMAGES = False


class InvalidImageError(ValueError):
    """Raised when the uploaded bytes are not a decodable image of an
    allowed type -- covers both "wrong magic bytes" and "magic bytes look
    right but Pillow can't actually decode it" (a mismatched/corrupt/hostile
    payload wearing a JPEG header, for example)."""


# ISO-BMFF (HEIF/HEIC) brand codes seen from phone cameras. The file starts
# with a `ftyp` box whose major/compatible brand is one of these.
_HEIF_BRANDS = frozenset(
    (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1")
)


def sniff_image_mime(data: bytes) -> str | None:
    """Magic-byte sniff only -- never trust the client-supplied filename or
    Content-Type (07-SECURITY.md section 4)."""
    if data.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(PNG_MAGIC):
        return "image/png"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    # HEIF/HEIC: bytes 4..8 are the "ftyp" box type, 8..12 the major brand.
    if _HEIF_AVAILABLE and len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic"
    return None


def output_mime_for(mime: str) -> str:
    """The mime the sanitized bytes are actually stored/served as. Identity
    for jpeg/png/webp; HEIC is transcoded to JPEG, so it maps to image/jpeg."""
    return _OUTPUT_MIME.get(mime, mime)


def extension_for_mime(mime: str) -> str:
    return _EXT_BY_MIME.get(mime, "bin")


# --- EXIF capture time -------------------------------------------------
# We deliberately destroy EXIF at intake (GPS in a photo is personal data --
# 07-SECURITY.md section 4). The *capture timestamp* is the one field the
# counter genuinely needs ("when was this parcel actually photographed?",
# which can differ from `received_at` when photos are uploaded in a later
# batch), so it is lifted out of the EXIF block *before* the strip and
# promoted to a real column. Nothing else from EXIF is kept.
_EXIF_IFD_POINTER = 0x8769
_TAG_DATETIME_ORIGINAL = 36867  # Exif IFD, when the shutter fired
_TAG_DATETIME_DIGITIZED = 36868  # Exif IFD, when it was written to storage
_TAG_DATETIME = 306  # Base IFD, "file changed" -- weakest, last resort
_TAG_OFFSET_ORIGINAL = 36881  # e.g. "+08:00"; many cameras omit it entirely
_TAG_OFFSET_DIGITIZED = 36882

# EXIF wall-clock has no timezone unless an OffsetTime* tag is present. When
# it is absent, interpret it as Taiwan time: this is a Taiwan mailroom and the
# photo was taken at the counter. Fixed +08:00 rather than ZoneInfo on purpose
# -- Taiwan has had no DST since 1979, and a fixed offset needs no tzdata in
# the container image.
_ASSUMED_CAMERA_TZ = timezone(timedelta(hours=8))

# A camera with a dead coin cell writes its epoch default (1970/1980/2000...).
# Showing "拍攝於 1970" is worse than showing nothing, so implausible stamps
# are dropped rather than stored.
_MIN_PLAUSIBLE_YEAR = 2000
_MAX_FUTURE_SKEW = timedelta(days=1)


def _parse_exif_offset(offset: object) -> timezone | None:
    """Parse an EXIF OffsetTime* value ("+08:00" / "-0500") into a tzinfo."""
    if not isinstance(offset, str):
        return None
    match = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", offset.strip().rstrip("\x00"))
    if match is None:
        return None
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    if delta > timedelta(hours=14):  # beyond any real UTC offset -> garbage
        return None
    return timezone(-delta if match.group(1) == "-" else delta)


def _parse_exif_datetime(raw: object, offset: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        naive = datetime.strptime(raw.strip().rstrip("\x00"), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    tz = _parse_exif_offset(offset) or _ASSUMED_CAMERA_TZ
    captured = naive.replace(tzinfo=tz).astimezone(timezone.utc)
    if captured.year < _MIN_PLAUSIBLE_YEAR:
        return None
    if captured > datetime.now(timezone.utc) + _MAX_FUTURE_SKEW:
        return None
    return captured


def extract_capture_time(data: bytes, mime: str) -> datetime | None:
    """Best-effort EXIF capture timestamp as an aware UTC datetime, or None.

    MUST be called on the *original* upload bytes -- `reencode_strip_exif`
    removes the EXIF segment this reads. Never raises: a photo with no EXIF
    (screenshots, re-saved images, most PNG/WEBP) or with corrupt EXIF is a
    normal case, not an upload error, and just yields None.
    """
    if mime not in _FORMAT_BY_MIME:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        exif = img.getexif()
        if not exif:
            return None
        try:
            sub = exif.get_ifd(_EXIF_IFD_POINTER) or {}
        except Exception:  # noqa: BLE001 - malformed Exif IFD -> fall back to base IFD
            sub = {}
        raw = (
            sub.get(_TAG_DATETIME_ORIGINAL)
            or sub.get(_TAG_DATETIME_DIGITIZED)
            or exif.get(_TAG_DATETIME)
        )
        offset = sub.get(_TAG_OFFSET_ORIGINAL) or sub.get(_TAG_OFFSET_DIGITIZED)
        return _parse_exif_datetime(raw, offset)
    except Exception:  # noqa: BLE001 - best-effort metadata read, never blocks an upload
        return None


def reencode_strip_exif(data: bytes, mime: str) -> tuple[bytes, int, int]:
    """Re-decode + re-encode `data` with Pillow, dropping all metadata
    (EXIF -- may carry GPS location, a personal-data leak per 07-SECURITY.md
    section 4 -- and any other ancillary chunks). Returns
    (sanitized_bytes, width, height).

    This also acts as a stronger content check than the magic-byte sniff
    alone: Pillow raising on `.load()` means the payload's header lied about
    what's inside, or the image is otherwise malformed/hostile (e.g. a
    decompression bomb -- `MAX_IMAGE_PIXELS` above, plus the explicit
    pre-load `img.size` check below, both surface as `InvalidImageError`
    like any other decode failure).
    """
    fmt = _FORMAT_BY_MIME.get(mime)
    if fmt is None:
        raise InvalidImageError(f"Unsupported image mime type: {mime}")

    try:
        img = Image.open(io.BytesIO(data))
        # Pillow's header parse is enough to know declared dimensions without
        # decoding pixel data -- check *before* the expensive `.load()` call
        # so a bomb is rejected up front rather than after doing the work it
        # was trying to force us to do.
        width, height = img.size
        if width * height > MAX_IMAGE_PIXELS:
            raise InvalidImageError(
                f"Image dimensions {width}x{height} exceed the {MAX_IMAGE_PIXELS}-pixel limit"
            )
        img.load()
    except InvalidImageError:
        raise
    except Exception as exc:  # noqa: BLE001 - any Pillow failure means "reject"
        raise InvalidImageError("Could not decode image data") from exc

    # Bake EXIF orientation into the pixel data *before* EXIF is dropped,
    # otherwise a sideways/upside-down phone photo would render wrong once
    # the orientation tag that would have corrected it is gone.
    img = ImageOps.exif_transpose(img)

    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    save_kwargs: dict = {}
    if fmt == "JPEG":
        save_kwargs["quality"] = 92
    # No `exif=` kwarg is passed, so Pillow writes the file with no EXIF
    # segment at all -- this *is* the "去 EXIF" step.
    img.save(buf, format=fmt, **save_kwargs)
    width, height = img.size
    return buf.getvalue(), width, height
