"""Upload / request-body size ceilings (M1-R1 blocking #1).

Reading an entire attacker-controlled body into memory before checking its
size (`await file.read()`, decoding a base64 field straight from a parsed
Pydantic model, ...) can OOM the process or fill disk. These constants are
the authoritative limits enforced at each specific read site (CSV import,
pickup signature) *in addition to* the generic
`app.security.body_limit.BodySizeLimitMiddleware` ceiling that protects
every endpoint regardless of payload shape.
"""

from __future__ import annotations

MAX_CSV_IMPORT_BYTES = 2 * 1024 * 1024  # 2 MB - 07-SECURITY.md upload limits discussion
MAX_SIGNATURE_PNG_BYTES = 512 * 1024  # 512 KB - a touch-signature PNG is tiny; this is generous

# base64 expands binary data by ~4/3; this is the max *encoded string*
# length that could still decode to <= MAX_SIGNATURE_PNG_BYTES, used to
# reject oversized payloads before spending time on the decode itself.
MAX_SIGNATURE_PNG_BASE64_CHARS = ((MAX_SIGNATURE_PNG_BYTES + 2) // 3) * 4 + 4

# M2-01 (04-AI-OCR.md / 07-SECURITY.md section 4): photo intake for OCR.
# "單檔 ≤15MB、單批 ≤30 張".
MAX_UPLOAD_FILES = 30
MAX_UPLOAD_FILE_BYTES = 15 * 1024 * 1024  # 15 MB per photo

# Ceiling for the *whole* multipart request body of POST /uploads. The
# generic app.security.body_limit.BodySizeLimitMiddleware default (20 MB) is
# far too small for a legitimate 30-photo batch, so that middleware carries a
# path-specific override for the uploads endpoint using this constant
# (theoretical max payload + multipart boundary/header overhead allowance).
MAX_UPLOAD_BATCH_BYTES = MAX_UPLOAD_FILES * MAX_UPLOAD_FILE_BYTES + 2 * 1024 * 1024
