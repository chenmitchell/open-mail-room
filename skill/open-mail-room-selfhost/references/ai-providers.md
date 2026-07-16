# AI OCR providers

The user brings their own key. This project ships no AI credits and pays for
nothing — say that plainly if they seem to expect OCR to "just work" out of the
box.

Configure providers in the app: **Admin → AI 設定**. Keys entered there are
encrypted at rest with the same key registry as personal data. Prefer the UI
over `AI_API_KEY` in `.env`, which sits in plaintext on disk.

## Choosing

| Provider | When it fits |
|---|---|
| **Google Gemini** | Cheap, fast, good on Chinese labels. A sensible default. |
| **OpenAI** | Strong general vision. Also covers any OpenAI-compatible endpoint via `AI_BASE_URL`. |
| **Anthropic Claude** | Strong on messy/handwritten labels. |
| **OpenRouter** | One key, many models. Useful for trying models without new accounts. |
| **Ollama (local)** | **Photos never leave the building.** The right answer when the org's rule is that mail images can't go to a third party. Costs hardware and accuracy instead of money. |

## Failover

Set several providers with priorities. If the first errors or times out, the
next takes over. Worth setting up: a single provider having a bad afternoon
otherwise means the front desk can't register parcels at all.

## Model naming — the trap worth avoiding

Prefer a concrete stable version (e.g. `gemini-2.5-flash`) over a moving alias
like `gemini-flash-latest`. Aliases repoint without warning, and the aggregate
endpoint behind them is the one that sheds load first — the symptom is
intermittent `503 UNAVAILABLE` that looks like a network problem and isn't.

Newer "thinking" models can also be slow enough to blow the OCR timeout for what
is, after all, reading a label. If OCR is timing out on a model that clearly
works, check whether extended thinking is on by default and turn it down — this
task doesn't need it.

## If OCR fails

Work through these in order; each rules out a whole class of cause:

1. **Read the actual error.** The UI surfaces the provider's real message on the
   confirm page. `google gemini request failed:` with nothing after it means the
   provider returned a body worth looking at in the container logs.
2. **Key valid? Billing on?** Free-tier keys hit hard quotas fast. A key that
   works in a curl test but 429s under load is a quota problem, not a bug.
3. **Model available to *that* key?** Model access varies per account. A 404 on
   a model name that exists publicly usually means it isn't enabled for them.
4. **Egress blocked?** A locked-down VPC can't reach the provider. Check from
   inside the container, not from the laptop.
5. **Photo too big / wrong format?** Oversized images are rejected at intake
   (15MB/file, 30/batch). HEIC is transcoded to JPEG automatically — but that
   support is best-effort: it needs `pillow-heif`'s native library to load in
   the image. If iPhone photos are being rejected as an unrecognized type while
   JPEGs sail through, that library didn't load, and the fix is in the image
   build, not the settings.

## Local Ollama

Runs on the same machine or the LAN. Point `AI_BASE_URL` at it.

The SSRF guard blocks private/internal addresses by default — that's what stops
a hostile endpoint from making the server probe its own network. Ollama on the
LAN trips it, which is correct behaviour, not a bug.

The fix is per-endpoint and lives in the admin UI: tick `allow_private_network`
on **that one AI provider config**. There is no global override, on purpose —
your Ollama box needing a LAN address is not a reason to let every webhook
target in the system reach your internal network.

Expect lower accuracy than a frontier model, especially on Chinese handwriting.
That's often an acceptable trade when the alternative is not being allowed to
use AI OCR at all — and the counter confirms every field anyway.

## The design principle worth conveying

AI fills the form; a human confirms it. Low-confidence fields are highlighted
for exactly this reason. The system is built so that a wrong OCR guess costs a
correction, not a misdelivered parcel — which is why "the AI got it wrong
sometimes" isn't a reason to distrust the system, and why nobody should be
tempted to auto-confirm drafts to save a click.

Deeper detail lives in the project's own `docs/AI-PROVIDERS.md`.
