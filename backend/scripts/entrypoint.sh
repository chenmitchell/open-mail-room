#!/bin/sh
set -eu

# Container entrypoint: ensure secrets -> migrate -> seed (carriers) -> serve.
#
# M0-R1 blocking #7: the previous CMD went straight to `uvicorn`, so a brand
# new deployment had no tables at all, and /readyz only did `SELECT 1`
# (which succeeds against an empty database), masking the problem. This
# script makes sure the schema is migrated before the API starts accepting
# traffic.
#
# SETUP-WIZARD: this no longer seeds an admin account (with a random
# password printed to this log) by default -- scripts/seed.py's admin
# auto-creation is now strictly opt-in (only runs when both ADMIN_EMAIL and
# ADMIN_PASSWORD are set, e.g. for automation/tests). The normal way to get
# the first administrator is the in-app first-run wizard at `/setup`
# (app/api/v1/setup.py): open the site once with zero admins in the
# database and it walks you through choosing your own email/display
# name/password, then locks itself. seed.py still always seeds the carrier
# list, which has nothing to do with credentials.
#
# ZEABUR-1: Zeabur's UI has no first-class "generate a random secret and
# remember it across redeploys" primitive, and hand-typing a SECRET_KEY /
# ENCRYPTION_KEY into the Zeabur env var form defeats the goal of "clone the
# repo, deploy, done" (also means the operator has to be trusted to generate
# a properly random 32-byte key by hand). Rather than require that: if the
# process environment doesn't already provide SECRET_KEY and at least one of
# ENCRYPTION_KEY/ENCRYPTION_KEYS, this script generates them itself on first
# boot and persists them to ${DATA_DIR}/secrets.env (on the same volume the
# SQLite DB and uploads live on -- DATA_DIR default /data, see
# app/config.py), then sources that file on every boot after. Re-generating
# on every restart would invalidate every session and make previously
# encrypted data (phone numbers, addresses, uploaded photos) permanently
# unreadable, so this only ever generates once -- if the file already
# exists, it's loaded as-is, never overwritten.

DATA_DIR="${DATA_DIR:-/data}"
SECRETS_FILE="${DATA_DIR}/secrets.env"

_gen_key() {
    # 32 random bytes, base64-encoded -- same format as the ENCRYPTION_KEY /
    # SECRET_KEY documented in .env.example. Prefer openssl (present in most
    # base images and what .env.example itself tells operators to run by
    # hand); fall back to python3 (always present in this image, since the
    # app itself needs it) if openssl isn't installed.
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 32
    else
        python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
    fi
}

if [ -z "${SECRET_KEY:-}" ] || { [ -z "${ENCRYPTION_KEY:-}" ] && [ -z "${ENCRYPTION_KEYS:-}" ]; }; then
    if [ -f "$SECRETS_FILE" ]; then
        echo "[entrypoint] SECRET_KEY/ENCRYPTION_KEY not both set via env; loading persisted secrets from ${SECRETS_FILE}..."
    else
        echo "[entrypoint] No SECRET_KEY/ENCRYPTION_KEY(S) provided and ${SECRETS_FILE} does not exist yet; generating and persisting new secrets (first boot)..."
        mkdir -p "$DATA_DIR"
        {
            echo "SECRET_KEY=$(_gen_key)"
            echo "ENCRYPTION_KEY=$(_gen_key)"
        } > "$SECRETS_FILE"
        chmod 600 "$SECRETS_FILE"
        echo "[entrypoint] Generated ${SECRETS_FILE}."
        echo "[entrypoint] IMPORTANT: 請備份 ${SECRETS_FILE}(此檔遺失將導致所有使用者 session 失效、且既有加密資料(電話/地址/上傳照片等)永久無法解密)。"
    fi
    # shellcheck disable=SC1090
    . "$SECRETS_FILE"
    export SECRET_KEY ENCRYPTION_KEY
fi

echo "[entrypoint] Running database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Seeding carrier list (idempotent, skips if already present)..."
python3 scripts/seed.py

echo "[entrypoint] 首次請開網站 /setup 建立管理員 (first run: open /setup in your browser to create the administrator account)."

echo "[entrypoint] Starting application server on port ${PORT:-8080}..."
# --proxy-headers + --forwarded-allow-ips='*': Zeabur's ingress terminates
# TLS in front of this container and reverse-proxies to it over plain HTTP,
# so without this flag the app would see every request as scheme=http (e.g.
# Secure cookies never getting set, X-Forwarded-Proto being ignored). '*' is
# safe here specifically because Zeabur's ingress is the *only* thing that
# can reach this container's $PORT -- there is no direct-to-container path
# for an external client to spoof X-Forwarded-* headers with (unlike a
# general-purpose "trust every proxy" setting on an exposed port).
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8080}" \
    --proxy-headers \
    --forwarded-allow-ips='*'
