# Environment variables

`deploy.sh` generates a working `.env` on first run, so most installs never need
to touch this file. Reach for it when something needs tuning, or when the user
asks what a particular setting does.

Anything not set falls back to a safe default in `backend/app/config.py`. The
app reads `.env` from the repo root; on a PaaS you set these as environment
variables in the dashboard instead.

## The ones that matter

| Variable | Notes |
|---|---|
| `ENCRYPTION_KEY` | base64 of exactly 32 bytes (`openssl rand -base64 32`). Decrypts every stored photo and encrypted personal field. **Lose it and the data is unrecoverable.** In production the app refuses to start if this isn't a valid 32-byte key — there is deliberately no weak-key fallback. |
| `SECRET_KEY` | base64 32 bytes. Signs sessions/JWT/CSRF. Rotating it logs everyone out; it does not damage data. |
| `DATABASE_URL` | Default `sqlite:///./data/openmailroom.db`. PostgreSQL: `postgresql://user:pass@postgres:5432/openmailroom`. SQLite is genuinely fine for a single office. |
| `ENVIRONMENT` | `production` (default) or `development`. Production enforces Secure cookies and strict key validation. Never set `development` on a real deployment. |
| `DOMAIN` | The public hostname. Drives Caddy's automatic HTTPS. |
| `PUBLIC_BASE_URL` | The URL used in outbound links (e.g. the welcome email's login link). Set it when the app sits behind a proxy and can't infer its own address. |

## Key rotation

| Variable | Notes |
|---|---|
| `ENCRYPTION_KEYS` | JSON map of version label → base64 key: `{"k1": "...", "k2": "..."}`. |
| `ENCRYPTION_ACTIVE_KEY` | Which of those versions *new* ciphertext is written with, e.g. `k2`. |

Ciphertext carries its key version as a prefix, so rows written under an old key
keep decrypting as long as that key stays in `ENCRYPTION_KEYS`. **Never remove a
key version that still has data written under it** — that's the same as deleting
that data. Rotation is: add `k2`, point `ENCRYPTION_ACTIVE_KEY` at it, keep `k1`
for the old rows.

The single-key `ENCRYPTION_KEY` form keeps working: it's registered as `k1`
for new writes, and also as `v1`, so ciphertext written by pre-rotation versions
of the app still decrypts.

## First admin

| Variable | Notes |
|---|---|
| `ADMIN_EMAIL` | Seeded admin account. |
| `ADMIN_PASSWORD` | Generated randomly by `deploy.sh` and printed once if not supplied. |

The user should change this password on first login. Don't set `ADMIN_PASSWORD`
to a value you chose for them, and don't read it back in chat.

## Auth tuning

| Variable | Default | Notes |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 15 | Session lifetime. |
| `LOGIN_MAX_ATTEMPTS` | | Failed logins before lockout. |
| `LOGIN_LOCKOUT_MINUTES` | | Lockout duration. |

## AI OCR

Normally configured in the admin UI (encrypted at rest), not here. These env
vars exist mainly for automated/CI deploys:

| Variable | Notes |
|---|---|
| `AI_PROVIDER` | `openai` / `anthropic` / `google` / `openrouter` / `ollama` |
| `AI_API_KEY` | Provider key. Prefer the UI so it's encrypted in the DB. |
| `AI_MODEL` | Pin a specific model. Prefer a concrete stable version over a `-latest` alias — aliases move under you and can start returning 503 under load. |
| `AI_BASE_URL` | For OpenRouter / local Ollama / any OpenAI-compatible endpoint. |
| `AI_DAILY_REQUEST_LIMIT` | Cost guard rail. |

## Email

| Variable | Notes |
|---|---|
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USE_TLS` | Standard SMTP. |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Credentials. The user enters these, not you. |
| `SMTP_FROM` | Envelope/from address. |
| `RESEND_API_KEY` | Shortcut: if set and `SMTP_HOST` isn't, mail goes via Resend's SMTP endpoint. Generic SMTP always wins if both are set, so self-hosters aren't pushed toward any particular vendor. |

## Paths and misc

| Variable | Notes |
|---|---|
| `DATA_DIR` | Where the DB and uploads live. Must be a persistent volume — this is the thing that has to survive a container restart. |
| `UPLOAD_DIR` | Encrypted photos/signatures. |
| `BRANDING_PATH` | Default `config/branding.yaml`. |
| `SERVE_FRONTEND` / `FRONTEND_DIST` | Single-container mode: the backend serves the built SPA. |
| `CORS_ALLOW_ORIGINS` | Only needed if the frontend is served from a different origin. |
| `LOG_LEVEL` | `info` default. |

## Things that are NOT environment variables

These are real features, configured elsewhere. Older copies of `.env.example`
listed env vars for some of them; nothing read those, so setting them did
nothing at all. If a user believes they've configured one of these via `.env`,
they haven't:

| Thing | Where it actually lives |
|---|---|
| Notification channels (LINE/Slack/Discord/Telegram/webhook) | Admin UI. Tokens are encrypted at rest in the settings table. |
| Letting a webhook or self-hosted AI endpoint reach private addresses | A per-endpoint `allow_private_network` toggle in the admin UI. Deliberately opt-in per endpoint — there is **no global switch** to disable the SSRF guard, because one endpoint needing a LAN address isn't a reason to let every endpoint reach the network. |
| Retention years, company name, logo, colours, pickup location, feature toggles | `config/branding.yaml` (retention can also be overridden at runtime via the settings table). |
| Backups | No built-in uploader. Back up the data volume + `ENCRYPTION_KEY` with whatever the org already uses. |
