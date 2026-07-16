"""Minimal RFC 9562 UUID version 7 generator.

No extra dependency is declared for this in requirements.txt, so we implement
the (small) algorithm ourselves: 48-bit millisecond Unix timestamp followed by
74 random bits, with the version/variant bits patched in per the spec.
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    unix_ts_ms = int(time.time() * 1000)
    ts_bytes = unix_ts_ms.to_bytes(6, byteorder="big")
    rand_bytes = bytearray(os.urandom(10))

    # Version 7 in the high nibble of byte 6 (0111xxxx).
    rand_bytes[0] = (rand_bytes[0] & 0x0F) | 0x70
    # Variant 10xxxxxx in byte 8.
    rand_bytes[2] = (rand_bytes[2] & 0x3F) | 0x80

    return uuid.UUID(bytes=bytes(ts_bytes) + bytes(rand_bytes))


def uuid7_str() -> str:
    return str(uuid7())
