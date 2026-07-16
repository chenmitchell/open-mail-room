# syntax=docker/dockerfile:1
#
# ZEABUR-1: single-container build for Zeabur (see docs/DEPLOY-ZEABUR.md).
#
# Zeabur's K3s nodes have no Docker CLI and terminate TLS at their own
# ingress in front of exactly one HTTP port per service -- there's no room
# for the docker-compose self-hosted topology (separate backend/frontend/
# Caddy containers on ports 80/443). This Dockerfile instead builds the
# frontend and bundles it into the backend image, which serves both the API
# and the SPA static files from a single process/port (see
# backend/app/main.py's SERVE_FRONTEND / _mount_spa).
#
# This file is intentionally separate from backend/Dockerfile and
# frontend/Dockerfile, which remain unmodified and are still what
# deploy/docker-compose.yml uses for the self-hosted (own VM + Caddy)
# deployment path. Do not merge the two -- they serve different topologies.
#
# Build context: the REPOSITORY ROOT (not backend/ or frontend/), since this
# stage needs to COPY from both backend/, frontend/, and config/.

# ---- Stage 1: build the frontend (Vue 3 + Vite) --------------------------
FROM node:22-slim AS frontend-build

WORKDIR /app/frontend

# Install deps first (better layer caching): only package manifests here so
# `npm run build` isn't re-run just because application source changed.
COPY frontend/package.json ./

# Plain `npm install` from package.json (no committed lockfile is relied on;
# a clean node:22 build environment resolves deps deterministically enough
# for our purposes). We intentionally avoid `npm ci`/`--frozen-lockfile` so a
# stale/out-of-sync lockfile can never fail the build.
RUN npm install --no-audit --no-fund

# Now the rest of the frontend source.
COPY frontend/ ./

# vite.config.ts reads ../config/branding.yaml (one level above frontend/,
# see frontend/vite.config.ts's loadBranding()) to bake app_name/colors/
# feature toggles into the build at compile time -- must exist at this
# relative path before `npm run build` runs, same as it does in a normal
# repo checkout. Missing/invalid branding.yaml is handled gracefully
# (falls back to defaults), so this COPY is still safe even for a repo
# checkout that never customized it.
COPY config/ /app/config/

RUN npm run build

# ---- Stage 2: backend (FastAPI) + the built frontend as static files -----
FROM python:3.12-slim AS backend

WORKDIR /app

# libmagic1: MIME sniffing for uploaded attachments (app/security/*).
# openssl: preferred source of randomness for scripts/entrypoint.sh's
# first-boot SECRET_KEY/ENCRYPTION_KEY generation (falls back to python3 -c
# if for some reason it's missing, but we install it so the primary path
# always works).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    openssl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser

# Same rationale as backend/Dockerfile: requirements.txt is a pinned
# lockfile, not `pip install -e .` (pyproject.toml has no [build-system]/
# [project] table).
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -U pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

# Aligned with backend/Dockerfile's layout: backend/'s contents land
# directly under /app (so /app/app/main.py, /app/scripts/entrypoint.sh,
# /app/alembic/, etc.) -- alembic.ini's script_location and
# scripts/entrypoint.sh's relative `scripts/seed.py` invocation both assume
# this layout, same as the existing single-service image.
COPY backend/ .

# config/branding.yaml at runtime too (app/config.py's load_branding, RC-FIX
# notification templates, retention_years, ...). Copied to a fixed,
# unambiguous path and pointed at explicitly via BRANDING_PATH below rather
# than relying on app/config.py's REPO_ROOT auto-detection (which assumes a
# source-tree layout that COPY backend/ . intentionally does not reproduce
# here -- see app/config.py's REPO_ROOT comment).
COPY config/ /app/config/

# The built SPA from stage 1, served by app/main.py when SERVE_FRONTEND=1.
COPY --from=frontend-build /app/frontend/dist /app/frontend_dist

RUN chmod +x scripts/entrypoint.sh

# ZEABUR-1 defaults. All overridable via Zeabur's service environment
# variables UI; see docs/DEPLOY-ZEABUR.md for the full list.
ENV SERVE_FRONTEND=1 \
    FRONTEND_DIST=/app/frontend_dist \
    DATA_DIR=/data \
    BRANDING_PATH=/app/config/branding.yaml \
    PORT=8080

# /data is where the Zeabur volume gets mounted (SQLite DB, uploads,
# secrets.env -- see app/config.py DATA_DIR / scripts/entrypoint.sh).
# Pre-create + chown here so a *fresh, empty* volume mounted at this path
# inherits usable ownership for appuser; if Zeabur's volume driver resets
# ownership on mount (platform-dependent, not something this Dockerfile can
# guarantee), the entrypoint will fail loudly rather than silently writing
# nowhere -- see docs/DEPLOY-ZEABUR.md's risk notes.
RUN mkdir -p /data && chown -R appuser:appuser /data /app

USER appuser

EXPOSE 8080

# Zeabur's ingress health-checks over HTTP to $PORT; curl isn't installed in
# this image (kept lean), so use python3 (already required by the app
# itself) instead.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/healthz', timeout=5)" || exit 1

CMD ["scripts/entrypoint.sh"]
