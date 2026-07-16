"""Pre-send image compression for the AI vision call (04-AI-OCR.md section
4: "送出前提示...影像前處理:上傳原圖保留存證,送 AI 前壓縮至長邊 1280px、
JPEG q80"). The encrypted original on disk is never touched -- this produces
a separate, smaller, throwaway copy that only ever exists in memory for the
duration of the provider call.
"""

from __future__ import annotations

import io
import warnings

from PIL import Image, ImageOps

from app.security.image_ops import InvalidImageError

DEFAULT_LONG_EDGE = 1280
DEFAULT_QUALITY = 80

# M2-R1 blocking #2: same decompression-bomb guard as app/security/image_ops.py
# (see that module's comment for the full rationale), applied here too --
# this function decodes the *already-stored* original a second time (to
# build the smaller AI-facing copy), so it needs its own guard rather than
# relying on the upload-time check having already run in the same process
# lifetime (Image.MAX_IMAGE_PIXELS is a global, but re-asserting it here
# means this module is safe even if imported/exercised independently of
# app.security.image_ops, e.g. in a future worker process).
MAX_IMAGE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
warnings.simplefilter("error", Image.DecompressionBombWarning)


def prepare_for_ai(
    data: bytes, *, long_edge: int = DEFAULT_LONG_EDGE, quality: int = DEFAULT_QUALITY
) -> bytes:
    try:
        img = Image.open(io.BytesIO(data))
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
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    width, height = img.size
    longest = max(width, height)
    if longest > long_edge:
        scale = long_edge / longest
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
