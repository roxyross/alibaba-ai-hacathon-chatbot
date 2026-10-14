# Multi-stage build for ROXY Personal AI Backend
FROM python:3.12-slim AS base

# Prevent Python from writing bytecode and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    ffmpeg \
    postgresql-client \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies layer
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application configuration and source code
COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY static ./static
COPY entrypoint.sh ./entrypoint.sh

# Ensure entrypoint is executable and has Unix line endings
RUN dos2unix ./entrypoint.sh && chmod +x ./entrypoint.sh

# Expose default container port
EXPOSE 8000

# Container health probe supporting dynamic $PORT
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health/live || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]

