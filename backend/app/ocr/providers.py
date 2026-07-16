"""Vision-OCR provider abstraction (04-AI-OCR.md section 2).

Every provider is called over plain `httpx` REST requests -- deliberately
*not* the vendor SDKs (`openai`, `anthropic`, `google-genai`, ...), per the
task's dependency-minimization rule. `OpenAICompatibleProvider` alone covers
OpenAI, OpenRouter, and any self-hosted OpenAI-compatible endpoint (Groq,
Together, LiteLLM, a local Ollama, ...) since they all speak the same
`/chat/completions` shape -- only `base_url`/`api_key`/`model` differ.

All three providers accept **multiple images in one request** (04 section 3:
"多圖一次送同一個 vision 請求") -- there is no per-image fallback path here
because every provider covered (OpenAI/Anthropic/Google/OpenRouter/
OpenAI-compatible) supports multi-image messages; a provider that genuinely
couldn't would simply be misconfigured, and its request would fail like any
other provider error (caught by the pipeline's retry/failover loop).

Each outbound call uses `httpx.AsyncClient(..., trust_env=False)` -- these
requests carry the (decrypted) provider API key and should only ever go
where this code explicitly points them (`base_url` / the vendor's fixed
endpoint), not wherever an ambient `HTTP_PROXY`/`ALL_PROXY` environment
variable happens to redirect them to.
"""

from __future__ import annotations

import base64
from typing import Protocol

import httpx

from app.models.enums import AiProvider
from app.ocr.schema import OCRResult, parse_ocr_json, to_ocr_result

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_TOKENS = 800

DEFAULT_BASE_URLS: dict[AiProvider, str] = {
    AiProvider.openai: "https://api.openai.com/v1",
    AiProvider.openrouter: "https://openrouter.ai/api/v1",
}

# Suggested defaults from 04-AI-OCR.md section 2 ("建議預設模型... 執行時再
# 驗證現況") -- used only when an admin leaves `model` blank.
DEFAULT_MODELS: dict[AiProvider, str] = {
    AiProvider.openai: "gpt-4o-mini",
    AiProvider.anthropic: "claude-haiku-4-5",
    AiProvider.google: "gemini-2.5-flash",
    AiProvider.openrouter: "openai/gpt-4o-mini",
}

# Rough per-1K-token USD pricing used only for the "粗估" cost_estimate
# (04-AI-OCR.md section 4). Not billing-accurate -- a coarse mini/haiku/flash
# -tier estimate is what the spec asks for.
_PRICING_USD_PER_1K_TOKENS: dict[AiProvider, tuple[float, float]] = {
    AiProvider.openai: (0.00015, 0.0006),
    AiProvider.anthropic: (0.001, 0.005),
    AiProvider.google: (0.000075, 0.0003),
    AiProvider.openrouter: (0.0005, 0.0015),
    AiProvider.openai_compatible: (0.0005, 0.0015),
}


def estimate_cost_usd(
    provider: AiProvider, tokens_in: int | None, tokens_out: int | None
) -> float:
    in_price, out_price = _PRICING_USD_PER_1K_TOKENS.get(provider, (0.0005, 0.0015))
    tin = tokens_in or 0
    tout = tokens_out or 0
    return round((tin / 1000) * in_price + (tout / 1000) * out_price, 6)


class ProviderError(RuntimeError):
    """Wraps any provider-call failure (network, HTTP status, malformed
    response) so the pipeline's retry/failover loop has one exception type
    to catch regardless of which vendor raised it."""


class VisionOCRProvider(Protocol):
    slug: str

    async def extract(
        self, images: list[bytes], *, prompt: str, model: str
    ) -> OCRResult: ...  # pragma: no cover - protocol definition


def _b64(image: bytes) -> str:
    return base64.b64encode(image).decode("ascii")


class OpenAICompatibleProvider:
    """OpenAI, OpenRouter, and any OpenAI-compatible `/chat/completions`
    endpoint (Groq, Together, LiteLLM, a local Ollama, ...)."""

    slug = "openai_compatible"

    def __init__(self, *, base_url: str, api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if not base_url:
            raise ProviderError("base_url is required for an OpenAI-compatible provider")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def extract(self, images: list[bytes], *, prompt: str, model: str) -> OCRResult:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for image in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{_b64(image)}"},
                }
            )
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            tokens_in = usage.get("prompt_tokens")
            tokens_out = usage.get("completion_tokens")
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai-compatible request failed: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"openai-compatible response malformed: {exc}") from exc

        parsed = parse_ocr_json(text)
        return to_ocr_result(parsed, tokens_in=tokens_in, tokens_out=tokens_out)


class AnthropicProvider:
    slug = "anthropic"

    API_URL = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, *, api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.api_key = api_key
        self.timeout = timeout

    async def extract(self, images: list[bytes], *, prompt: str, model: str) -> OCRResult:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for image in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": _b64(image),
                    },
                }
            )
        payload = {
            "model": model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(self.API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            text = data["content"][0]["text"]
            usage = data.get("usage") or {}
            tokens_in = usage.get("input_tokens")
            tokens_out = usage.get("output_tokens")
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic request failed: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"anthropic response malformed: {exc}") from exc

        parsed = parse_ocr_json(text)
        return to_ocr_result(parsed, tokens_in=tokens_in, tokens_out=tokens_out)


class GoogleGeminiProvider:
    slug = "google"

    def __init__(self, *, api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.api_key = api_key
        self.timeout = timeout

    async def extract(self, images: list[bytes], *, prompt: str, model: str) -> OCRResult:
        parts: list[dict] = [{"text": prompt}]
        for image in images:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": _b64(image)}})
        gen_config: dict = {"temperature": 0, "maxOutputTokens": MAX_OUTPUT_TOKENS}
        # Gemini 2.5 models turn "thinking" ON by default, which adds many
        # seconds of latency (enough to blow past the request timeout and the
        # confirm page's 90s poll window) for zero benefit on a pure
        # label-OCR extraction. Disable it for 2.5 models. Older models
        # (2.0/1.5) reject thinkingConfig, so only send it when applicable.
        if "2.5" in model:
            gen_config["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": gen_config,
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={self.api_key}"
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(url, json=payload)
            if response.status_code >= 400:
                # Surface Google's own error body verbatim -- it's JSON with a
                # precise reason (PERMISSION_DENIED / API key not valid / model
                # not found / quota) that a bare status line would hide.
                raise ProviderError(
                    f"google gemini HTTP {response.status_code}: {response.text[:600]}"
                )
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            usage = data.get("usageMetadata") or {}
            tokens_in = usage.get("promptTokenCount")
            tokens_out = usage.get("candidatesTokenCount")
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            # repr(exc) keeps the exception *class* (ConnectTimeout(),
            # ConnectError(...), ReadTimeout(), ...) even when str(exc) is empty
            # -- a network/egress failure was otherwise logged as
            # "...failed: " with nothing after it, hiding the real cause.
            raise ProviderError(f"google gemini request failed: {exc!r}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"google gemini response malformed: {exc}") from exc

        parsed = parse_ocr_json(text)
        return to_ocr_result(parsed, tokens_in=tokens_in, tokens_out=tokens_out)


_GOOGLE_MODEL_FALLBACKS = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)


async def list_google_models(
    api_key: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> list[str]:
    """Return model ids (short name) that support generateContent for this key."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resp = await client.get(url)
    resp.raise_for_status()
    out: list[str] = []
    for m in resp.json().get("models", []) or []:
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" in methods:
            out.append(str(m.get("name", "")).split("/")[-1])
    return out


async def resolve_google_model(api_key: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Auto-pick a vision-capable flash model the given key actually supports.

    Avoids hard-coding a model id that a particular key/region may not have.
    Falls back to a known-good default if ListModels is unavailable.
    """
    try:
        names = await list_google_models(api_key, timeout=timeout)
    except Exception:  # noqa: BLE001 - discovery best-effort; fall back below
        return _GOOGLE_MODEL_FALLBACKS[0]
    if not names:
        return _GOOGLE_MODEL_FALLBACKS[0]
    nameset = set(names)
    # Prefer a specific, stable, vision-capable flash model. The "*-latest"
    # aliases route to a shared capacity pool that frequently returns
    # 503 UNAVAILABLE ("model is currently experiencing high demand") under
    # load -- confirmed in production -- so they are used only as a last
    # resort, never preferred.
    for preferred in (
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-1.5-flash",
    ):
        if preferred in nameset:
            return preferred
    non_latest_flash = sorted(
        (n for n in names if "flash" in n and "latest" not in n and "lite" not in n),
        reverse=True,
    )
    if non_latest_flash:
        return non_latest_flash[0]
    any_flash = sorted((n for n in names if "flash" in n), reverse=True)
    if any_flash:
        return any_flash[0]
    return names[0]


def default_model_for(provider: AiProvider) -> str | None:
    return DEFAULT_MODELS.get(provider)


def build_provider(
    provider: AiProvider, *, base_url: str | None, api_key: str
) -> VisionOCRProvider:
    """Factory: turn an `ai_provider_configs` row's (provider, base_url,
    decrypted api_key) into a callable `VisionOCRProvider`."""
    if provider in (AiProvider.openai, AiProvider.openrouter, AiProvider.openai_compatible):
        resolved_base_url = base_url or DEFAULT_BASE_URLS.get(provider)
        if not resolved_base_url:
            raise ProviderError(
                f"base_url is required for provider '{provider.value}' "
                "(no built-in default for openai_compatible)"
            )
        return OpenAICompatibleProvider(base_url=resolved_base_url, api_key=api_key)
    if provider == AiProvider.anthropic:
        return AnthropicProvider(api_key=api_key)
    if provider == AiProvider.google:
        return GoogleGeminiProvider(api_key=api_key)
    raise ProviderError(f"Unsupported AI provider: {provider!r}")
