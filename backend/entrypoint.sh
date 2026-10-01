#!/usr/bin/env bash
set -e

echo "==> [ROXY Backend] Starting container initialization..."

# Wait for PostgreSQL database if DATABASE_URL is configured
if [ -n "$DATABASE_URL" ]; then
  echo "==> [ROXY Backend] Checking database connectivity..."
  python - << 'EOF'
import os
import sys
import time
from urllib.parse import urlparse
import socket

db_url = os.environ.get("DATABASE_URL", "").strip()
if not db_url:
    sys.exit(0)

# Normalize asyncpg / postgres scheme
clean_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
try:
    parsed = urlparse(clean_url)
    host = parsed.hostname or "db"
    port = parsed.port or 5432
except Exception:
    host = "db"
    port = 5432

print(f"==> [ROXY Backend] Probing database connection at {host}:{port}...")
start_time = time.time()
timeout = 60
connected = False

while time.time() - start_time < timeout:
    try:
        with socket.create_connection((host, port), timeout=2):
            connected = True
            print(f"==> [ROXY Backend] Database at {host}:{port} is reachable!")
            break
    except (OSError, ConnectionRefusedError):
        time.sleep(1)

if not connected:
    print(f"==> [ROXY Backend] WARNING: Timeout reached ({timeout}s) waiting for database {host}:{port}. Attempting to continue...")
EOF

  # Run Alembic migrations if alembic.ini is present
  if [ -f "alembic.ini" ]; then
    echo "==> [ROXY Backend] Running Alembic database migrations (alembic upgrade head)..."
    alembic upgrade head || echo "==> [ROXY Backend] Warning: Alembic migrations returned a non-zero exit code, proceeding..."
  fi
fi

echo "==> [ROXY Backend] Executing application command: $@"
exec "$@"
