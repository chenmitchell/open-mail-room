# PaaS / single-container deploy (Zeabur and similar)

For hosts where there's no docker CLI and you can't run `deploy.sh` — a managed
platform that builds from your repo and runs one container. The backend serves
the built frontend, so it's a single service, not two.

The project's `docs/DEPLOY-ZEABUR.md` is the authoritative walkthrough. This
file covers what to watch for.

## Shape of it

1. Fork/push the repo to GitHub.
2. New project → Add Service → Deploy from GitHub → pick the repo.
3. **Attach a persistent volume mounted at `/data`.** Do this before first boot.
4. Set `ENVIRONMENT=production`.
5. Bind a domain in the platform's Domain settings — the ingress issues and
   terminates TLS, the container never sees a certificate.

## The volume is the whole ballgame

`/data` holds the SQLite database, the encrypted photos, **and** the
auto-generated `secrets.env`. Without a persistent volume the container gets a
fresh filesystem on every deploy — which means new encryption keys every deploy,
which means yesterday's photos are permanently unreadable and nobody notices
until someone opens an old record.

Verify it's real before trusting it:

```bash
df -h /data         # should show a mounted filesystem, not the overlay root
```

## Keys generate themselves — then never change

On first boot `scripts/entrypoint.sh` finds no `SECRET_KEY`/`ENCRYPTION_KEY` in
the environment, generates both, and writes `/data/secrets.env` (chmod 600),
logging a reminder to back it up. **It only does this once** — every later boot
reuses that file. That's what makes redeploys safe.

Two consequences worth stating to the user:

- **`/data/secrets.env` is the only copy of the encryption key.** Not in the
  dashboard, not in git, not in the env vars — one file on one volume. Back it
  up somewhere else, today.
- Setting `ENCRYPTION_KEY` as an env var later **overrides** the file. Point at
  the wrong value and every existing photo stops decrypting. If keys are already
  working from the file, leave the env vars empty.

Then it runs `alembic upgrade head` and the idempotent seed (admin account +
default carriers). If `ADMIN_PASSWORD` isn't set, seed generates one and prints
it to the deployment log **once**. Fish it out of the logs before they roll.

## Environment variables

Required:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` — drives Secure cookies and strict key validation |

Deliberately leave unset unless you have a specific reason:

| Variable | Why leave it |
|---|---|
| `SECRET_KEY` / `ENCRYPTION_KEY` | Auto-generated into `/data/secrets.env` and reused. Setting them by hand is how you break decryption. |
| `PORT` | The platform injects it. |
| `DOMAIN` | Compose/Caddy-only. Bind the domain in the dashboard instead. |
| `CORS_ALLOW_ORIGINS` | Same-origin deploy needs no CORS. |
| `DATA_DIR` | `/data`, matching the volume. |

## Every deploy logs everyone out

A deploy restarts the container, which drops in-memory sessions. Data and keys
survive; sessions don't. This looks alarming ("it logged me out, did we lose
everything?") and is harmless — worth saying before it happens rather than
after.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Photos won't decrypt after a redeploy | No persistent volume, or `ENCRYPTION_KEY` set to something other than what wrote them. |
| `/readyz` fails, `/healthz` fine | Migrations didn't run. Check deployment logs for the `alembic upgrade head` step. |
| Login works then instantly 401s | `ENVIRONMENT` isn't `production`, so cookies aren't `Secure` behind the TLS-terminating ingress. |
| Can't find the admin password | Printed once in the first deployment's logs. If it's rolled off, reset via `ADMIN_PASSWORD` + redeploy. |

## Testing

Test through the bound domain over HTTPS. Testing via the container's internal
address bypasses the ingress, the TLS termination, and the forwarded-proto
header — the three things that actually break here. A pass from inside the
container tells you almost nothing.
