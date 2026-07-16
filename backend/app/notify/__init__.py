"""Notification delivery subsystem (M3-01, docs/plan/05-NOTIFICATIONS.md).

Layout:
- `base`: the `NotifyChannel` Protocol + `RenderedMessage`/`SendResult`.
- `adapters/`: one module per channel (line/telegram/slack/discord/email/webhook).
- `templates`: message template rendering + confidential masking.
- `settings_store`: encrypted-at-rest settings helpers (channel tokens etc).
- `registry`: loads settings -> builds the right adapter for a channel.
- `binding_codes`: 6-digit LINE/Telegram binding-code issue/verify.
- `worker`: background delivery (retry/backoff/dead-letter) + orphan sweep.
- `scheduler`: daily reminder/unclaimed sweep.
"""
