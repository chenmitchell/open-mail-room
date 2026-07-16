FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for PIL/image processing and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Install dependencies from the pinned lockfile (requirements.txt), not an
# editable `pip install -e .` -- pyproject.toml has no [build-system]/
# [project] table, so `-e .` is not a valid install target here.
COPY requirements.txt ./

RUN pip install --no-cache-dir -U pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Entrypoint runs `alembic upgrade head` then the idempotent seed script
# before starting the API (07-SECURITY / M0-R1 #7): a fresh deployment must
# end up with a migrated schema and a usable admin account, not a 500 loop.
RUN chmod +x scripts/entrypoint.sh

# Switch to non-root user
USER appuser

# Healthcheck: verify API is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/healthz || exit 1

# Run application
CMD ["scripts/entrypoint.sh"]
