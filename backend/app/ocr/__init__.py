"""AI vision-OCR subsystem (04-AI-OCR.md).

- `app.ocr.schema`: the structured extraction result + JSON parsing.
- `app.ocr.prompts`: the versioned system prompt.
- `app.ocr.image_prep`: pre-send image compression (long edge 1280px, JPEG q80).
- `app.ocr.providers`: the `VisionOCRProvider` protocol + OpenAI-compatible /
  Anthropic / Google Gemini implementations (raw httpx REST calls, no
  per-vendor SDK dependency).
- `app.ocr.postprocess`: tracking_no <-> carrier regex cross-validation.
- `app.ocr.pipeline`: the background job runner (failover, retries, budget
  enforcement, persistence).
"""
