"""Encrypted-at-rest file storage for attachments (pickup signatures, etc).

Files are AES-256-GCM encrypted with the same key registry used for
encrypted DB columns (see app.models.types.encrypt_bytes/decrypt_bytes) and
written under Settings.upload_dir. We never store plaintext image bytes on
disk (07-SECURITY.md section 3/4).
"""

from __future__ import annotations

import hashlib
import struct
import uuid
from pathlib import Path

from app.config import get_settings
from app.models.types import decrypt_bytes, encrypt_bytes

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_IHDR_TYPE = b"IHDR"

# Generous ceiling for a touch-signature pad -- guards against a maliciously
# crafted PNG whose IHDR chunk claims an absurd width/height (a classic
# decompression-bomb-style resource-exhaustion vector against whatever later
# tries to decode/render the image) (M1-R1 suggestion: "PNG 結構/尺寸驗證").
MAX_PNG_DIMENSION = 4000

FILE_AAD = "attachments.file"


class InvalidPngError(ValueError):
    pass


def validate_png(data: bytes) -> None:
    """Structural validation beyond the magic bytes: the IHDR chunk must be
    present where PNG requires it, and its declared width/height must be
    sane. Not a full PNG parser/decoder -- just enough to reject obviously
    malformed or hostile input before it's written to disk."""
    if not data.startswith(PNG_MAGIC):
        raise InvalidPngError("Not a valid PNG file (bad magic bytes)")
    if len(data) < 24 or data[12:16] != PNG_IHDR_TYPE:
        raise InvalidPngError("Not a valid PNG file (missing IHDR chunk)")

    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        raise InvalidPngError("Invalid PNG dimensions")
    if width > MAX_PNG_DIMENSION or height > MAX_PNG_DIMENSION:
        raise InvalidPngError(
            f"PNG dimensions ({width}x{height}) exceed the {MAX_PNG_DIMENSION}px limit"
        )


def png_dimensions(data: bytes) -> tuple[int | None, int | None]:
    """Best-effort width/height from the PNG IHDR chunk. Returns (None, None)
    if the data is too short/malformed to parse -- this is a convenience
    for the attachments.width/height columns, not a security check."""
    try:
        if len(data) < 24:
            return None, None
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    except Exception:
        return None, None


def _upload_root() -> Path:
    root = Path(get_settings().upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_encrypted_file(plaintext: bytes, *, subdir: str, extension: str = "bin") -> dict:
    """Encrypts `plaintext` and writes it under UPLOAD_DIR/subdir/<uuid>.<ext>.enc.

    Returns a dict with file_path (relative to UPLOAD_DIR, forward-slash
    separated so it's portable across OSes), sha256 (of the *plaintext*,
    for integrity verification after decryption), and size_bytes (plaintext
    size).
    """
    root = _upload_root()
    target_dir = root / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    sha256 = hashlib.sha256(plaintext).hexdigest()
    filename = f"{uuid.uuid4().hex}.{extension}.enc"
    full_path = target_dir / filename

    ciphertext = encrypt_bytes(plaintext, aad=FILE_AAD)
    full_path.write_bytes(ciphertext)

    relative_path = f"{subdir}/{filename}"
    return {
        "file_path": relative_path,
        "sha256": sha256,
        "size_bytes": len(plaintext),
    }


def read_encrypted_file(relative_path: str) -> bytes:
    root = _upload_root()
    full_path = root / relative_path
    ciphertext = full_path.read_bytes()
    return decrypt_bytes(ciphertext, aad=FILE_AAD)


def delete_encrypted_file(relative_path: str) -> None:
    """Best-effort delete of an attachment's on-disk ciphertext (M4-01
    retention sweep: "匿名化...+attachment 實體檔刪除" / "刪除"). A missing
    file is not an error -- a retention sweep re-run after a partial prior
    run (e.g. the row's DB update committed but the process died before this
    unlink executed) must not fail the whole sweep.
    """
    root = _upload_root()
    full_path = root / relative_path
    full_path.unlink(missing_ok=True)
