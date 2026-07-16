"""Unit tests for app.ocr.schema (JSON parsing/tolerance) and
app.ocr.prompts (versioned prompt assembly) -- 04-AI-OCR.md section 3.
"""

from __future__ import annotations

import pytest

from app.models.enums import MailType
from app.ocr.prompts import PROMPT_VERSION, build_prompt
from app.ocr.schema import OCRParseError, parse_ocr_json, to_ocr_result


def test_parse_ocr_json_plain():
    text = '{"tracking_no": "123", "confidence": 0.8}'
    assert parse_ocr_json(text) == {"tracking_no": "123", "confidence": 0.8}


def test_parse_ocr_json_strips_markdown_fence():
    text = '```json\n{"tracking_no": "123", "confidence": 0.5}\n```'
    assert parse_ocr_json(text) == {"tracking_no": "123", "confidence": 0.5}


def test_parse_ocr_json_strips_bare_fence_no_language_tag():
    text = '```\n{"confidence": 0.1}\n```'
    assert parse_ocr_json(text) == {"confidence": 0.1}


def test_parse_ocr_json_tolerates_surrounding_prose():
    text = 'Sure, here is the JSON:\n{"confidence": 0.7}\nHope that helps!'
    assert parse_ocr_json(text) == {"confidence": 0.7}


def test_parse_ocr_json_raises_on_garbage():
    with pytest.raises(OCRParseError):
        parse_ocr_json("not json at all, no braces")


def test_parse_ocr_json_raises_on_malformed_braces():
    with pytest.raises(OCRParseError):
        parse_ocr_json("{not: valid, json}")


def test_to_ocr_result_strips_non_alnum_from_tracking_no():
    result = to_ocr_result({"tracking_no": "AB-1234 5678", "confidence": 0.9})
    assert result.tracking_no == "AB12345678"


def test_to_ocr_result_null_tracking_no_stays_none():
    result = to_ocr_result({"tracking_no": None, "confidence": 0.5})
    assert result.tracking_no is None


def test_to_ocr_result_clamps_confidence_range():
    assert to_ocr_result({"confidence": 5}).confidence == 1.0
    assert to_ocr_result({"confidence": -3}).confidence == 0.0
    assert to_ocr_result({"confidence": "not-a-number"}).confidence == 0.0


def test_to_ocr_result_strips_recipient_suffix_is_left_to_model():
    # Field cleanup only strips whitespace/None; suffix removal
    # ("先生/小姐/收") is the model's job per the prompt, not ours.
    result = to_ocr_result({"recipient_name": "  陳大文  ", "confidence": 0.9})
    assert result.recipient_name == "陳大文"


def test_to_ocr_result_carries_token_counts_through():
    result = to_ocr_result({"confidence": 0.9}, tokens_in=120, tokens_out=40)
    assert result.tokens_in == 120
    assert result.tokens_out == 40


def test_build_prompt_default_has_no_letter_or_barcode_addendum():
    prompt = build_prompt()
    # letter-specific addendum absent by default...
    assert "收件人常居中直式" not in prompt
    assert "單號已知" not in prompt
    assert "tracking_no" in prompt
    # ...but the always-on multi-photo / front-back / who-sent-to-whom guidance is present
    assert "多張照片" in prompt
    assert "誰寄給誰" in prompt


def test_build_prompt_letter_mail_type_adds_addendum():
    prompt = build_prompt(mail_type=MailType.letter)
    assert "信封" in prompt


def test_build_prompt_barcode_known_adds_addendum():
    prompt = build_prompt(barcode_known=True)
    assert "單號已知" in prompt


def test_build_prompt_both_addenda_combine():
    prompt = build_prompt(mail_type=MailType.letter, barcode_known=True)
    assert "信封" in prompt
    assert "單號已知" in prompt


def test_prompt_version_is_stable_identifier():
    assert PROMPT_VERSION == "v3"
