#!/bin/bash
set -euo pipefail

# Open Mail Room idempotent deployment script
# Brings up the full stack (app + Caddy for automatic HTTPS, optional
# PostgreSQL) on any Docker host. Safe to re-run: existing .env keys are
# never regenerated.
# Usage: ./deploy.sh [DOMAIN=example.com] [POSTGRES_PROFILE=1]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DOMAIN="${DOMAIN:-}"
USE_POSTGRES="${POSTGRES_PROFILE:-}"

echo "=== Open Mail Room Deployment ==="
echo "Repository: $REPO_ROOT"
echo "Domain: ${DOMAIN:-localhost (self-signed)}"
echo ""

# Step 1: Navigate to repo root
cd "$REPO_ROOT"

# Step 2: Git pull (fail gracefully if not a git repo during testing)
echo "[1/6] Pulling latest changes..."
if git rev-parse --git-dir >/dev/null 2>&1; then
  git pull --ff-only || echo "Warning: git pull failed (might already be up-to-date)"
else
  echo "Warning: Not a git repository, skipping git pull"
fi
echo "✓ Git pull complete"
echo ""

# Step 3: Create or verify .env file
echo "[2/6] Setting up .env..."
if [ ! -f .env ]; then
  echo "Creating .env with generated secrets..."

  # Generate random 32-byte base64 strings for keys
  SECRET_KEY=$(openssl rand -base64 32)
  ENCRYPTION_KEY=$(openssl rand -base64 32)
  POSTGRES_PASSWORD=$(openssl rand -base64 16)
  # M0-R1 blocking #8: never ship a hardcoded default admin password. If the
  # caller didn't set ADMIN_PASSWORD explicitly, generate a random one and
  # print it once below (it is not recoverable afterwards).
  ADMIN_PASSWORD_GENERATED=0
  if [ -z "${ADMIN_PASSWORD:-}" ]; then
    ADMIN_PASSWORD=$(openssl rand -base64 18)
    ADMIN_PASSWORD_GENERATED=1
  fi

  cat > .env <<ENVEOF
# Open Mail Room Environment Variables
# Generated at $(date -u +%Y-%m-%dT%H:%M:%SZ)

# Database
DATABASE_URL=sqlite:///./data/openmailroom.db
POSTGRES_PASSWORD=$POSTGRES_PASSWORD

# Security (CRITICAL: Keep backup of ENCRYPTION_KEY!)
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY

# Fail-safe default is "production" in the app itself, but set it
# explicitly here too so it's visible/auditable in the generated .env
# (M0-R1 blocking #2 -- Secure cookies, no dev key fallback).
ENVIRONMENT=production

# Admin account
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@example.com}
ADMIN_PASSWORD=$ADMIN_PASSWORD

# Domain (for HTTPS)
DOMAIN=${DOMAIN:-localhost}

ENVEOF

  echo ""
  echo "!!! CRITICAL: ENCRYPTION KEY BACKUP REQUIRED !!!"
  echo "Your encryption key is:"
  echo "  $ENCRYPTION_KEY"
  echo ""
  echo "This key is needed to decrypt personal data fields and photos."
  echo "Loss of this key means permanent data loss."
  echo ""
  echo "Recommendation: Save it to a secure location (password manager, HSM, etc.)"
  echo ""

  if [ "$ADMIN_PASSWORD_GENERATED" -eq 1 ]; then
    echo "!!! Generated admin password (save this now, shown once): $ADMIN_PASSWORD !!!"
    echo ""
  fi
else
  echo ".env file exists, skipping generation"
fi
echo "✓ .env ready"
echo ""

# Step 3b: Build frontend (if not already built)
echo "[3a/6] Building frontend..."
if [ ! -d "frontend/dist" ] || [ -z "$(ls -A frontend/dist 2>/dev/null)" ]; then
  if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    cd frontend
    if command -v pnpm >/dev/null 2>&1; then
      pnpm install && pnpm build
    else
      npm install && npm run build
    fi
    cd ..
    echo "✓ Frontend built"
  else
    echo "⚠ frontend directory not found or package.json missing, skipping frontend build"
  fi
else
  echo "✓ Frontend already built (frontend/dist exists)"
fi
echo ""

# Step 4: Build and pull images
echo "[3b/6] Building/pulling Docker images..."
if [ -n "$USE_POSTGRES" ]; then
  echo "Using PostgreSQL profile..."
  docker compose --profile postgres pull --ignore-pull-failures
  docker compose --profile postgres build
else
  echo "Using SQLite (default)..."
  docker compose pull --ignore-pull-failures
  docker compose build
fi
echo "✓ Docker images ready"
echo ""

# Step 5: Start containers
echo "[4/6] Starting containers (restart: unless-stopped)..."
if [ -n "$USE_POSTGRES" ]; then
  docker compose --profile postgres up -d
else
  docker compose up -d
fi
echo "✓ Containers started"
echo ""

# Step 6: Health check with timeout
echo "[5/6] Waiting for services to be ready (timeout: 120s)..."
MAX_ATTEMPTS=24
ATTEMPT=0
HEALTHY=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  ATTEMPT=$((ATTEMPT + 1))

  # Try both HTTP and HTTPS
  if curl -sf http://localhost/healthz >/dev/null 2>&1 || \
     curl -sfk https://localhost/healthz >/dev/null 2>&1; then
    HEALTHY=1
    echo "✓ Health check passed"
    break
  fi

  echo "  Attempt $ATTEMPT/$MAX_ATTEMPTS: Waiting for services..."
  sleep 5
done

echo ""
if [ $HEALTHY -eq 0 ]; then
  echo "✗ Health check failed after ${MAX_ATTEMPTS}*5 seconds"
  echo ""
  echo "Debugging logs:"
  echo "--- Backend logs ---"
  docker compose logs backend | tail -30
  echo ""
  echo "--- Caddy logs ---"
  docker compose logs caddy | tail -30
  echo ""
  exit 1
fi

echo "[6/6] Deployment complete!"
echo ""
echo "=== Summary ==="
echo "Frontend: https://${DOMAIN:-localhost}"
echo "API: https://${DOMAIN:-localhost}/api"
echo "Caddy admin: http://localhost:2019 (local only)"
echo ""
echo "Next steps:"
echo "1. Change admin password (currently from ADMIN_PASSWORD env)"
echo "2. Backup ENCRYPTION_KEY and database files (data/openmailroom.db)"
echo "3. Set up automated backups"
echo ""
echo "For support, refer to docs/INSTALL.md"
