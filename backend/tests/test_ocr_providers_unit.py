"""Unit tests for app.ocr.providers (the VisionOCRProvider implementations,
mocked at the httpx.AsyncClient.post layer -- 不打真實 AI API) and
app.ocr.postprocess (tracking_no <-> carrier regex cross-validation).
"""

from __future__ import annotations

import httpx
import pytest

from app.models.carrier import Carrier
from app.models.enums import AiProvider, CarrierKind
from app.ocr.postprocess import cross_validate_tracking
from app.ocr.providers import (
    AnthropicProvider,
    GoogleGeminiProvider,
    OpenAICompatibleProvider,
    ProviderError,
    build_provider,
    default_model_for,
    estimate_cost_usd,
)
from app.ocr.schema import OCRResult


class _FakeResponse:
    def __init__(self, json_data, status_code=200, text=""):
        self._json = json_data
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)

    def json(self):
        return self._json


def _patch_post(monkeypatch, handler):
    async def fake_post(self, url, json=None, headers=None, **kwargs):
        return handler(url, json, headers)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


async def test_openai_compatible_provider_extract_success(monkeypatch):
    def handler(url, json, headers):
        assert url == "https://api.openai.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer sk-test"
        return _FakeResponse(
            {
                "choices": [
                    {"message": {"content": '{"tracking_no": "AB123", "confidence": 0.8}'}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )

    _patch_post(monkeypatch, handler)
    provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-test")
    result = await provider.extract([b"fake-image-bytes"], prompt="p", model="gpt-4o-mini")
    assert result.tracking_no == "AB123"
    assert result.confidence == 0.8
    assert result.tokens_in == 10
    assert result.tokens_out == 5


async def test_openai_compatible_provider_requires_base_url():
    with pytest.raises(ProviderError):
        OpenAICompatibleProvider(base_url="", api_key="sk-test")


async def test_openai_compatible_provider_wraps_http_error(monkeypatch):
    def handler(url, json, headers):
        return _FakeResponse({}, status_code=500)

    _patch_post(monkeypatch, handler)
    provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-test")
    with pytest.raises(ProviderError):
        await provider.extract([b"img"], prompt="p", model="gpt-4o-mini")


async def test_openai_compatible_provider_wraps_malformed_response(monkeypatch):
    def handler(url, json, headers):
        return _FakeResponse({"unexpected": "shape"})

    _patch_post(monkeypatch, handler)
    provider = OpenAICompatibleProvider(base_url="https://api.openai.com/v1", api_key="sk-test")
    with pytest.raises(ProviderError):
        await provider.extract([b"img"], prompt="p", model="gpt-4o-mini")


async def test_anthropic_provider_extract_success(monkeypatch):
    def handler(url, json, headers):
        assert url == AnthropicProvider.API_URL
        assert headers["x-api-key"] == "sk-ant-test"
        assert json["messages"][0]["content"][1]["source"]["media_type"] == "image/jpeg"
        return _FakeResponse(
            {
                "content": [
                    {"text": '{"recipient_name": "\u9673\u5927\u6587", "confidence": 0.6}'}
                ],
                "usage": {"input_tokens": 200, "output_tokens": 30},
            }
        )

    _patch_post(monkeypatch, handler)
    provider = AnthropicProvider(api_key="sk-ant-test")
    result = await provider.extract([b"img"], prompt="p", model="claude-haiku-4-5")
    assert result.recipient_name == "陳大文"
    assert result.tokens_in == 200
    assert result.tokens_out == 30


async def test_google_gemini_provider_extract_success(monkeypatch):
    def handler(url, json, headers):
        assert "generativelanguage.googleapis.com" in url
        assert "key=sk-google-test" in url
        return _FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"carrier_guess": "tcat", "confidence": 0.4}'}]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 90, "candidatesTokenCount": 20},
            }
        )

    _patch_post(monkeypatch, handler)
    provider = GoogleGeminiProvider(api_key="sk-google-test")
    result = await provider.extract([b"img"], prompt="p", model="gemini-flash-latest")
    assert result.carrier_guess == "tcat"
    assert result.tokens_in == 90
    assert result.tokens_out == 20


async def test_google_gemini_provider_wraps_http_error(monkeypatch):
    def handler(url, json, headers):
        return _FakeResponse({}, status_code=429)

    _patch_post(monkeypatch, handler)
    provider = GoogleGeminiProvider(api_key="sk-google-test")
    with pytest.raises(ProviderError):
        await provider.extract([b"img"], prompt="p", model="gemini-flash-latest")


async def test_build_provider_openai_uses_default_base_url():
    provider = build_provider(AiProvider.openai, base_url=None, api_key="sk-x")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://api.openai.com/v1"


async def test_build_provider_openai_compatible_requires_base_url():
    with pytest.raises(ProviderError):
        build_provider(AiProvider.openai_compatible, base_url=None, api_key="sk-x")


async def test_build_provider_openai_compatible_with_custom_base_url_eg_ollama():
    provider = build_provider(
        AiProvider.openai_compatible, base_url="http://localhost:11434/v1", api_key="unused"
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "http://localhost:11434/v1"


async def test_build_provider_anthropic_and_google():
    assert isinstance(
        build_provider(AiProvider.anthropic, base_url=None, api_key="k"), AnthropicProvider
    )
    assert isinstance(
        build_provider(AiProvider.google, base_url=None, api_key="k"), GoogleGeminiProvider
    )


def test_default_model_for_known_providers():
    assert default_model_for(AiProvider.openai) == "gpt-4o-mini"
    assert default_model_for(AiProvider.anthropic) is not None


def test_estimate_cost_usd_zero_tokens_is_zero():
    assert estimate_cost_usd(AiProvider.openai, None, None) == 0.0


def test_estimate_cost_usd_scales_with_tokens():
    low = estimate_cost_usd(AiProvider.openai, 100, 50)
    high = estimate_cost_usd(AiProvider.openai, 1000, 500)
    assert 0 < low < high


async def _make_carrier(db_session, *, slug, pattern) -> Carrier:
    carrier = Carrier(name=slug, slug=slug, kind=CarrierKind.courier, tracking_pattern=pattern)
    db_session.add(carrier)
    await db_session.commit()
    await db_session.refresh(carrier)
    return carrier


async def test_cross_validate_tracking_matches_pattern(db_session):
    await _make_carrier(db_session, slug="tcat", pattern=r"^\d{12}$")
    result = OCRResult(
        tracking_no="123456789012",
        carrier_guess="tcat",
        sender_name=None,
        sender_org=None,
        sender_phone=None,
        recipient_name=None,
        recipient_dept_hint=None,
        is_handwritten=None,
        confidence=0.9,
    )
    validation = await cross_validate_tracking(db_session, result)
    assert validation["carrier_id"] is not None
    assert validation["confidence"] == 0.9
    assert validation["warnings"] == []


async def test_cross_validate_tracking_pattern_mismatch_lowers_confidence(db_session):
    await _make_carrier(db_session, slug="tcat", pattern=r"^\d{12}$")
    result = OCRResult(
        tracking_no="not-a-valid-number",
        carrier_guess="tcat",
        sender_name=None,
        sender_org=None,
        sender_phone=None,
        recipient_name=None,
        recipient_dept_hint=None,
        is_handwritten=None,
        confidence=0.9,
    )
    validation = await cross_validate_tracking(db_session, result)
    assert validation["confidence"] <= 0.5
    assert "tracking_no_pattern_mismatch" in validation["warnings"]


async def test_cross_validate_tracking_unknown_carrier_guess_warns(db_session):
    result = OCRResult(
        tracking_no="123456789012",
        carrier_guess="not_a_real_carrier",
        sender_name=None,
        sender_org=None,
        sender_phone=None,
        recipient_name=None,
        recipient_dept_hint=None,
        is_handwritten=None,
        confidence=0.9,
    )
    validation = await cross_validate_tracking(db_session, result)
    assert validation["carrier_id"] is None
    assert any(w.startswith("unknown_carrier_guess") for w in validation["warnings"])


async def test_cross_validate_tracking_infers_carrier_when_guess_missing(db_session):
    await _make_carrier(db_session, slug="tcat", pattern=r"^\d{12}$")
    result = OCRResult(
        tracking_no="123456789012",
        carrier_guess=None,
        sender_name=None,
        sender_org=None,
        sender_phone=None,
        recipient_name=None,
        recipient_dept_hint=None,
        is_handwritten=None,
        confidence=0.9,
    )
    validation = await cross_validate_tracking(db_session, result)
    assert validation["carrier_id"] is not None
