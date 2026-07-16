#!/bin/bash
set -euo pipefail

# Generate self-signed certificate for internal/private network deployment
# Usage: ./selfsigned.sh [DOMAIN]

DOMAIN="${1:-localhost}"
DAYS_VALID="${2:-365}"
KEY_FILE="./ssl/private.key"
CERT_FILE="./ssl/cert.pem"
CSR_FILE="./ssl/cert.csr"

echo "=== Open Mail Room Self-Signed Certificate Generator ==="
echo "Domain: $DOMAIN"
echo "Validity: $DAYS_VALID days"
echo ""

# Create ssl directory
mkdir -p ssl

# Generate private key
echo "[1/4] Generating private key..."
openssl genrsa -out "$KEY_FILE" 2048
chmod 600 "$KEY_FILE"
echo "✓ Private key: $KEY_FILE (chmod 600)"
echo ""

# Generate certificate signing request
echo "[2/4] Generating certificate signing request..."
openssl req -new \
  -key "$KEY_FILE" \
  -out "$CSR_FILE" \
  -subj "/CN=$DOMAIN/O=Open Mail Room/C=TW" \
  -addext "subjectAltName=DNS:$DOMAIN,DNS:*.${DOMAIN}"
echo "✓ CSR: $CSR_FILE"
echo ""

# Self-sign the certificate
echo "[3/4] Self-signing certificate..."
openssl x509 -req \
  -days "$DAYS_VALID" \
  -in "$CSR_FILE" \
  -signkey "$KEY_FILE" \
  -out "$CERT_FILE" \
  -extensions "subjectAltName=DNS:$DOMAIN,DNS:*.${DOMAIN}"
echo "✓ Certificate: $CERT_FILE"
echo ""

# Update Caddyfile for self-signed mode
echo "[4/4] Updating Caddyfile for self-signed certificate..."
cat > ./Caddyfile.selfsigned <<'INNEREOF'
{
	# Disable automatic HTTPS; use self-signed cert instead
	auto_https off
	admin off
}

:443, :80 {
	tls /etc/caddy/certs/cert.pem /etc/caddy/certs/private.key

	# Security headers (same as production). No path matcher -> applies
	# globally to every response from this site block (M0-R1 suggestion:
	# `header /` only matched the literal root path "/", not everything).
	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "SAMEORIGIN"
		Referrer-Policy "strict-origin-when-cross-origin"
		# camera=(self): M2's in-browser photo capture uses getUserMedia from
		# our own origin. camera=() would block that entirely.
		Permissions-Policy "camera=(self), microphone=(), payment=()"
	}

	# HTTP redirect to HTTPS
	@http {
		protocol http
	}
	redir @http https://{host}{uri} permanent

	# API reverse proxy to backend
	@api {
		path /api/*
	}
	reverse_proxy @api backend:8000 {
		header_down -Server
	}

	# Health endpoints
	handle /healthz {
		reverse_proxy backend:8000
	}

	handle /readyz {
		reverse_proxy backend:8000
	}

	# Serve frontend
	root /srv/frontend
	try_files {path} /index.html
	file_server
}
INNEREOF

echo "✓ Caddyfile.selfsigned created"
echo ""

# Cleanup intermediate files
rm -f "$CSR_FILE"

echo "=== Certificate Ready ==="
echo ""
echo "Files created:"
echo "  - $KEY_FILE"
echo "  - $CERT_FILE"
echo "  - ./Caddyfile.selfsigned"
echo ""
echo "To use self-signed certificate:"
echo ""
echo "1. Copy certificates into docker-compose volume:"
echo "   mkdir -p <certs-volume-path>"
echo "   cp $KEY_FILE <certs-volume-path>/private.key"
echo "   cp $CERT_FILE <certs-volume-path>/cert.pem"
echo ""
echo "2. Update docker-compose.yml to mount certs:"
echo "   caddy:"
echo "     volumes:"
echo "       - ./Caddyfile.selfsigned:/etc/caddy/Caddyfile:ro"
echo "       - ./ssl:/etc/caddy/certs:ro"
echo ""
echo "3. Run deployment:"
echo "   docker compose up -d"
echo ""
echo "4. On client machine, add to trusted certificates (or use -k with curl)"
echo ""
echo "WARNING: Self-signed certificates will trigger browser warnings."
echo "This is normal for internal-only deployments."
echo ""
echo "For production/public deployment, use DOMAIN env var in deploy.sh"
echo "to enable automatic Let's Encrypt certificates via Caddy."
