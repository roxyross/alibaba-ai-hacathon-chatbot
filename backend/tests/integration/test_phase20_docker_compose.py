"""Phase 20 — Docker Compose One-Click Stack Integration Tests.

Validates:
1. Docker Compose root orchestration manifest, services, volumes, networks, and health checks.
2. Backend Dockerfile, entrypoint script, and database migration automation.
3. Frontend Vite Nginx multi-stage Dockerfile and SPA reverse proxy routing.
4. Fast probe health check endpoints (/health, /health/live, /health/ready, /api/v1/health).
5. Docker CLI validation parity.
"""

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml  # type: ignore[import-untyped]

from app.main import app

# -----------------------------------------------------------------------------
# 1. Manifest & Architecture Verification
# -----------------------------------------------------------------------------

def test_docker_compose_manifest_structure() -> None:
    """Verify docker-compose.yml exists and declares all required services and networks."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_path = repo_root / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"

    with open(compose_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "services" in config, "docker-compose.yml must define 'services'"
    services = config["services"]

    # Verify primary services
    assert "db" in services, "db service (Postgres + pgvector) missing from docker-compose.yml"
    assert "redis" in services, "redis service missing from docker-compose.yml"
    assert "backend" in services, "backend service missing from docker-compose.yml"
    assert "frontend" in services, "frontend service missing from docker-compose.yml"

    # Verify optional profiles
    assert "frontend-prod" in services, "frontend-prod service missing"
    assert "nextjs-frontend" in services, "nextjs-frontend service missing"

    # Verify DB configuration
    db = services["db"]
    assert "pgvector" in db["image"], "db image must use pgvector"
    assert "healthcheck" in db, "db must have a healthcheck"
    assert "roxy_pgdata" in str(db.get("volumes", [])), "db must mount roxy_pgdata volume"

    # Verify Redis configuration
    redis = services["redis"]
    assert "redis" in redis["image"], "redis image must use redis:7-alpine"
    assert "healthcheck" in redis, "redis must have a healthcheck"
    assert "roxy_redisdata" in str(redis.get("volumes", [])), "redis must mount roxy_redisdata volume"

    # Verify Backend dependencies & healthcheck
    backend = services["backend"]
    assert "depends_on" in backend, "backend must depend on db and redis"
    deps = backend["depends_on"]
    assert "db" in deps and deps["db"].get("condition") == "service_healthy"
    assert "redis" in deps and deps["redis"].get("condition") == "service_healthy"
    assert "healthcheck" in backend, "backend must have a healthcheck probe"

    # Verify volumes & networks
    assert "volumes" in config
    assert "roxy_pgdata" in config["volumes"]
    assert "roxy_redisdata" in config["volumes"]
    assert "networks" in config
    assert "roxy_network" in config["networks"]


def test_dockerfile_and_container_artifacts() -> None:
    """Verify all Dockerfiles, entrypoint scripts, and Nginx configurations exist."""
    repo_root = Path(__file__).resolve().parents[3]

    # Backend Dockerfile & Entrypoint
    backend_dockerfile = repo_root / "backend" / "Dockerfile"
    backend_entrypoint = repo_root / "backend" / "entrypoint.sh"
    backend_dockerignore = repo_root / "backend" / ".dockerignore"

    assert backend_dockerfile.exists(), "backend/Dockerfile missing"
    assert backend_entrypoint.exists(), "backend/entrypoint.sh missing"
    assert backend_dockerignore.exists(), "backend/.dockerignore missing"

    entrypoint_content = backend_entrypoint.read_text(encoding="utf-8")
    assert "alembic upgrade head" in entrypoint_content, "entrypoint.sh must run Alembic migrations"
    assert "exec \"$@\"" in entrypoint_content, "entrypoint.sh must exec container CMD"

    # Frontend Dockerfile & Nginx Conf
    frontend_dockerfile = repo_root / "frontend" / "Dockerfile"
    frontend_nginx = repo_root / "frontend" / "nginx.conf"
    frontend_dockerignore = repo_root / "frontend" / ".dockerignore"

    assert frontend_dockerfile.exists(), "frontend/Dockerfile missing"
    assert frontend_nginx.exists(), "frontend/nginx.conf missing"
    assert frontend_dockerignore.exists(), "frontend/.dockerignore missing"

    nginx_content = frontend_nginx.read_text(encoding="utf-8")
    assert "location /api/" in nginx_content, "nginx.conf must reverse proxy /api/ to backend"
    assert "proxy_pass http://backend:8000/api/;" in nginx_content
    assert "try_files $uri $uri/ /index.html;" in nginx_content, "nginx.conf must support SPA rewrite"

    # Next.js Frontend Dockerfile
    nextjs_dockerfile = repo_root / "nextjs-frontend" / "Dockerfile"
    assert nextjs_dockerfile.exists(), "nextjs-frontend/Dockerfile missing"


# -----------------------------------------------------------------------------
# 2. Container Health Probe Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_container_healthcheck_endpoints() -> None:
    """Verify healthcheck probes used by Docker container orchestrators respond with 200 OK."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Standard root health
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "ok"

        # Liveness probe
        res_live = await client.get("/health/live")
        assert res_live.status_code == 200
        assert res_live.json()["status"] == "ok"

        # Readiness probe
        res_ready = await client.get("/health/ready")
        assert res_ready.status_code == 200
        assert res_ready.json()["status"] == "ok"

        # Versioned API health
        res_v1 = await client.get("/api/v1/health")
        assert res_v1.status_code == 200
        assert res_v1.json()["status"] == "ok"


# -----------------------------------------------------------------------------
# 3. Docker CLI Syntax Validation
# -----------------------------------------------------------------------------

def test_docker_compose_cli_validation() -> None:
    """Verify docker compose CLI can parse and validate the compose configuration."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        pytest.skip("Docker CLI not found on host machine, skipping CLI config validation")

    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [docker_bin, "compose", "--profile", "prod", "--profile", "nextjs", "config"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"docker compose config failed: {result.stderr}"
    assert "roxy-backend" in result.stdout
    assert "roxy-db" in result.stdout
    assert "roxy-frontend" in result.stdout
    assert "roxy-redis" in result.stdout
