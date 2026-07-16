---
name: open-mail-room-selfhost
description: Deploy and set up Open Mail Room, the open-source self-hostable office mailroom system (收發室系統), on the user's own server. Use this skill whenever the user wants to install, deploy, self-host, set up, upgrade, back up, or troubleshoot Open Mail Room — including phrasings like "架一個收發室系統", "幫我裝 Open Mail Room", "公司包裹管理系統自己架", "mailroom 部署", "我想自己架那個包裹系統", or when they point at the open-mail-room repo and ask to get it running. Also use it when they ask how to back up the encryption key, import the employee directory, connect an AI provider for OCR, or set up notification channels for this system. Prefer this skill over generic Docker/deployment advice for anything involving this project.
---

# Self-hosting Open Mail Room

Open Mail Room is an office mailroom system: the front desk photographs a parcel
label, AI reads the recipient and tracking number, the system notifies that
person to collect it, and collection is captured with a signature.

Your job with this skill is to get it running on the user's own infrastructure
and hand it over in a state where they can actually use it on Monday morning —
not just "the container is up".

## What matters most here

This system stores photographs of other people's mail and their personal
contact details. Two things follow from that, and they shape the whole install:

1. **The encryption key is the data.** `ENCRYPTION_KEY` decrypts every stored
   photo and every encrypted personal field. Lose it and the data is gone
   forever — no support ticket recovers it. Leak it and someone else can read
   the mail. Getting this backed up, off the box, is the single most important
   step in this process, and it is not done until the human confirms it.

2. **Secrets are the user's to handle, not yours.** You never type, paste, or
   read back their AI provider API key, their SMTP password, or their admin
   password. Guide them to enter those themselves — in the app's own settings
   UI, or in their own editor. If you find yourself about to echo a secret into
   the transcript, stop; that transcript is a place secrets don't belong.

## Step 1 — Ask two questions before touching anything

The whole install branches on these, so ask up front rather than guessing:

- **Where does it run?** A server they control with Docker (the normal case), or
  a PaaS like Zeabur (no docker CLI, single container)?
- **How do people reach it?** A public domain with real HTTPS, or an internal
  hostname on the office LAN with a self-signed certificate?

If they don't know, the default that fits most offices: their own small VM +
Docker Compose + a real domain. Automatic HTTPS comes free that way, and phone
cameras need HTTPS — a browser will refuse `getUserMedia` on plain HTTP from a
non-localhost origin, which means the camera page silently won't work. Say this
out loud if they're leaning toward "just run it on HTTP for now"; it's the
single most common way this install ends up broken.

## Step 2 — Preflight

Check before installing, so failures happen in a sentence rather than halfway
through a build:

```bash
docker --version && docker compose version   # Compose v2 (the plugin), not docker-compose
openssl version
git --version
df -h .                                       # photos accumulate; 50GB+ is a sane floor
ss -ltnp 2>/dev/null | grep -E ':(80|443)\s' || echo "ports 80/443 free"
```

If something else already owns 80/443 (another Caddy, nginx, a k8s ingress),
**stop and tell the user** rather than starting the stack — you'll take down
whatever is already serving on that box. That situation calls for either the
PaaS path (`references/zeabur.md`) or putting Open Mail Room behind the existing
reverse proxy, which is a decision for the user to make, not for you to assume.

## Step 3 — Get the code and deploy

```bash
git clone https://github.com/YOUR-USERNAME/open-mail-room.git
cd open-mail-room/deploy
chmod +x deploy.sh
DOMAIN=mailroom.example.com ./deploy.sh
```

Substitute their real domain. For an intranet install with a self-signed
certificate, omit `DOMAIN` and see `references/intranet.md`. For PostgreSQL
instead of the default SQLite, prefix `POSTGRES_PROFILE=1`.

`deploy.sh` is idempotent — safe to re-run. On the first run it generates
`SECRET_KEY`, `ENCRYPTION_KEY`, and an admin password into `.env`; on later runs
it sees `.env` exists and leaves those keys alone. That property matters: it
means "re-run the deploy" is always a safe suggestion, and it means the keys are
generated exactly once, at this moment.

The script then builds the frontend, brings up the containers, and polls
`/healthz` for up to 120 seconds.

## Step 4 — Stop. Back up the encryption key.

The script prints `ENCRYPTION_KEY` and the generated admin password once, to the
terminal, and never again.

Do not paste those values into the chat, and do not save them to a file in the
project directory. Instead, put the responsibility where it belongs:

> The deploy script has printed your `ENCRYPTION_KEY` and admin password in the
> terminal. Please copy the encryption key into your password manager now —
> somewhere that is not this server. If this server's disk dies and that key
> only existed on it, every stored photo and every encrypted personal field
> becomes permanently unreadable. Tell me once it's saved and I'll carry on.

Wait for them to actually confirm. This is the one place in the install where
pressing on without the human is genuinely harmful, and where a nudge from you
now saves them from a disaster months later that nobody will be able to undo.

While you're here, confirm `.env` is ignored by git:

```bash
git check-ignore -v .env && echo "OK: .env is ignored"
```

If that prints nothing, `.env` is trackable and a single `git add -A` would push
their keys to GitHub. Fix `.gitignore` before doing anything else.

## Step 5 — Verify it's actually working

"The container started" is not the same as "it works". Check the two endpoints
that mean different things:

```bash
curl -sf https://mailroom.example.com/healthz && echo " <- process is alive"
curl -sf https://mailroom.example.com/readyz  && echo " <- DB reachable AND migrated"
```

`/healthz` only says the process is up. `/readyz` queries the database, so it's
the one that catches "migrations never ran" — the failure that otherwise shows
up later as a confusing 500 on first login.

Test from a real browser at the real URL, not from inside the container and not
via `localhost`. A `localhost` test bypasses TLS, the proxy, and the cookie's
`Secure` flag — all three of which are exactly what breaks in production. If
login works from `localhost` but not from the domain, you've learned nothing
except that you tested the wrong thing.

Then hand over the admin account. Which of two things happens depends on
whether `ADMIN_PASSWORD` was set, and it's worth knowing which before you tell
the user what to expect:

- **`deploy.sh` was used** (the normal path): it wrote both `ADMIN_EMAIL` and
  `ADMIN_PASSWORD` into `.env`, so the seed step already created the admin
  before anyone opened a browser. The user lands on the **login page**, not a
  setup wizard, and signs in with the password the script printed in Step 4.
  `/setup` returns `409 SETUP_ALREADY_DONE` — that's expected, not a fault.
- **`ADMIN_PASSWORD` was left unset** (some PaaS installs): no admin exists yet,
  so the site shows the **first-run setup wizard** and the user chooses their
  own password there.

Either way, have them change the password from the UI once they're in — a
password that was printed to a terminal and possibly scrolled through a
deployment log isn't one to keep. They type it; you don't.

## Step 6 — Make it useful

A running install with an empty employee directory can't route a single parcel.
Walk them through these, in this order — each one unblocks the next:

1. **Employee directory** — import CSV or add manually. Without this, name
   matching has nothing to match against. Include nicknames/aliases; Taiwanese
   offices route a lot of mail on 綽號, and the fuzzy matcher uses them.
2. **Departments + a fixed contact per department** — mail addressed to a
   company or department rather than a person gets routed to that contact.
   Departments without a contact silently can't receive department mail.
3. **AI provider key** — Admin → AI settings. They paste their own key into the
   app; it's encrypted at rest. They bring their own key: this project ships no
   AI credits. If photos must not leave the building, point them at local Ollama
   (`references/ai-providers.md`).
4. **Notification channels** — Email/LINE/Slack/Discord/Telegram/webhook. Until
   one exists, recipients are never told their parcel arrived, which is the
   entire point of the system.
5. **Branding** — `config/branding.yaml`: company name, logo, colour, pickup
   location, retention years, feature toggles. No code changes needed.

Finish by having them run one real parcel end-to-end: photograph a label →
confirm the OCR draft → check the notification arrives → collect and sign. One
real round trip surfaces more than any amount of checklist-ticking, and it's the
thing that tells them the system is theirs now.

## Upgrades and backups

```bash
cd open-mail-room && git pull && cd deploy && ./deploy.sh   # re-run is safe
```

What to back up, and why each matters:

- `.env` — **the encryption key.** Without it the rest of the backup is noise.
- the data volume (SQLite DB + encrypted photos) — the actual records.
- `config/branding.yaml` — cheap to lose, annoying to redo.

A backup of the database without the key is worthless. Say so plainly when
setting up their backup job; people back up the obvious big directory and skip
the 40-character line that makes it readable.

## When it doesn't work

| Symptom | What's actually going on |
|---|---|
| Camera page does nothing on a phone | Not HTTPS. Browsers block camera access on insecure origins. |
| `/healthz` OK but `/readyz` fails | DB unreachable or migrations never ran. Check the app container's logs. |
| Health check times out in deploy.sh | Ports 80/443 taken by something else, or DNS not pointing here yet. |
| Login works on localhost, fails on the domain | Cookie `Secure`/proxy headers — test only via the real URL. |
| OCR fails or is slow | Provider key/quota/model. `references/ai-providers.md` covers failover. |
| Notifications never arrive | No channel configured, or the employee never bound theirs. |
| Photos won't open after a restore | `ENCRYPTION_KEY` doesn't match the one they were written with. |

Container logs are the first stop for anything server-side:

```bash
cd open-mail-room/deploy && docker compose logs --tail=100 app
```

## Reference files

Read these only when the situation calls for it:

- `references/zeabur.md` — PaaS / single-container deploys (no docker CLI)
- `references/intranet.md` — LAN install with a self-signed certificate
- `references/ai-providers.md` — provider choice, local Ollama, failover
- `references/env-vars.md` — every environment variable and what it does

The project's own `docs/` (INSTALL.md, FAQ.md, AI-PROVIDERS.md, BRANDING.md,
API-INTEGRATION.md) is the deeper source of truth — send the user there for
anything this skill doesn't cover.
