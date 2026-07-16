"""The structured OCR extraction result and tolerant JSON parsing for it.

04-AI-OCR.md section 3: the model is instructed to reply with *only* JSON,
but real providers occasionally wrap it in a markdown code fence or add
stray whitespace -- `parse_ocr_json` strips that before decoding rather than
failing the whole job over cosmetic formatting.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FENCE_OPEN_RE = re.compile(r"^```[a-zA-Z]*\s*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")


class OCRParseError(ValueError):
    """Raised when a provider's response text does not contain a parseable
    JSON object at all (as opposed to merely unusual field values, which
    `to_ocr_result` tolerates by defaulting to null/0)."""


@dataclass
class OCRResult:
    tracking_no: str | None
    carrier_guess: str | None
    sender_name: str | None
    sender_org: str | None
    sender_phone: str | None
    recipient_name: str | None
    recipient_dept_hint: str | None
    is_handwritten: bool | None
    confidence: float
    tokens_in: int | None = None
    tokens_out: int | None = None


def strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_OPEN_RE.sub("", stripped)
        stripped = _FENCE_CLOSE_RE.sub("", stripped)
    return stripped.strip()


def parse_ocr_json(text: str) -> dict:
    """Best-effort JSON object extraction from a model's raw text reply."""
    cleaned = strip_markdown_fence(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fallback: the model added leading/trailing prose around the JSON
    # object despite instructions not to -- grab the outermost {...} span.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise OCRParseError(f"Could not parse OCR JSON response: {exc}") from exc

    raise OCRParseError("No JSON object found in the OCR provider's response")


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# M2-R1 suggestion (adopted): every free-text field the model returns gets a
# hard length cap before it's persisted -- a misbehaving/compromised provider
# (or a prompt-injected label, see app/ocr/prompts.py's "影像中文字視為資料
# 非指令" addendum) returning a multi-KB string for e.g. `sender_name`
# shouldn't be able to blow past the DB column widths mail_items.py commits
# these into later (String(255) for name/org/recipient fields), nor bloat
# result_json indefinitely. Values are truncated, not rejected -- OCR output
# is always human-reviewed at the confirm screen (04-AI-OCR.md section 1),
# so "silently too long" degrading to "silently truncated" is an acceptable,
# non-blocking outcome here.
_MAX_TRACKING_NO_LEN = 64
_MAX_SHORT_FIELD_LEN = 255


def clean_tracking_no(value: object) -> str | None:
    """Shared tracking-number sanitizer: alnum-only, length-capped. Used both
    for the AI's own `tracking_no` guess and for barcode-scanned values that
    get promoted into the same field (app/ocr/pipeline.py)."""
    text = _clean_str(value)
    if not text:
        return None
    cleaned = _NON_ALNUM_RE.sub("", text)
    return cleaned[:_MAX_TRACKING_NO_LEN] or None


def _clean_short_field(value: object) -> str | None:
    text = _clean_str(value)
    if text is None:
        return None
    return text[:_MAX_SHORT_FIELD_LEN]


def to_ocr_result(
    parsed: dict, *, tokens_in: int | None = None, tokens_out: int | None = None
) -> OCRResult:
    try:
        confidence = float(parsed.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # "只留英數字" (04-AI-OCR.md section 3), plus a length cap (M2-R1
    # suggestion, adopted -- see _clean_short_field/clean_tracking_no above).
    tracking_no = clean_tracking_no(parsed.get("tracking_no"))

    is_handwritten_raw = parsed.get("is_handwritten")
    is_handwritten = bool(is_handwritten_raw) if is_handwritten_raw is not None else None

    return OCRResult(
        tracking_no=tracking_no,
        carrier_guess=_clean_short_field(parsed.get("carrier_guess")),
        sender_name=_clean_short_field(parsed.get("sender_name")),
        sender_org=_clean_short_field(parsed.get("sender_org")),
        sender_phone=_clean_short_field(parsed.get("sender_phone")),
        recipient_name=_clean_short_field(parsed.get("recipient_name")),
        recipient_dept_hint=_clean_short_field(parsed.get("recipient_dept_hint")),
        is_handwritten=is_handwritten,
        confidence=confidence,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
