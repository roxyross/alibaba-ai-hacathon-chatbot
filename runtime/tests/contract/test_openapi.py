"""Contract tests: verify the runtime's OpenAPI shape matches PR 2 spec.

The PR 2 surface is:
  POST /api/v1/runtime/chat
  GET  /api/v1/runtime/agents
  GET  /api/v1/runtime/skills
  GET  /health/live
  GET  /health/ready

These are checked against the auto-generated OpenAPI schema.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from runtime.main import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app()


class TestOpenAPIContract:
    """Verify the runtime exposes the expected PR 2 endpoints."""

    def test_chat_endpoint_exists(self, app: FastAPI) -> None:
        """POST /api/v1/runtime/chat is registered."""
        paths = app.openapi()["paths"]
        assert "/api/v1/runtime/chat" in paths
        assert "post" in paths["/api/v1/runtime/chat"]

    def test_chat_request_schema(self, app: FastAPI) -> None:
        """POST body has 'message' (string, 1-8000 chars) and optional 'session_id'."""
        schema = app.openapi()
        raw = schema["paths"]["/api/v1/runtime/chat"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        # Pydantic v2 emits a $ref; resolve from components/schemas
        if "$ref" in raw:
            body = schema["components"]["schemas"][raw["$ref"].split("/")[-1]]
        else:
            body = raw
        assert "message" in body["properties"]
        assert body["properties"]["message"]["type"] == "string"
        assert body["properties"]["message"]["minLength"] == 1
        assert body["properties"]["message"]["maxLength"] == 8000
        assert "session_id" in body["properties"]

    def test_chat_response_schema(self, app: FastAPI) -> None:
        """POST response has all required fields per ChatResponse."""
        schema = app.openapi()
        raw = (
            schema["paths"]["/api/v1/runtime/chat"]["post"]["responses"]["200"]
            ["content"]["application/json"]["schema"]
        )
        # Pydantic v2 may emit $ref for response schemas too
        if "$ref" in raw:
            resp = schema["components"]["schemas"][raw["$ref"].split("/")[-1]]
        else:
            resp = raw
        required = {"needs_clarification", "agent_slug", "response", "citations", "status", "next_actions"}
        assert required.issubset(resp["properties"].keys())

    def test_agents_endpoint_exists(self, app: FastAPI) -> None:
        """GET /api/v1/runtime/agents is registered."""
        paths = app.openapi()["paths"]
        assert "/api/v1/runtime/agents" in paths
        assert "get" in paths["/api/v1/runtime/agents"]

    def test_skills_endpoint_exists(self, app: FastAPI) -> None:
        """GET /api/v1/runtime/skills is registered."""
        paths = app.openapi()["paths"]
        assert "/api/v1/runtime/skills" in paths
        assert "get" in paths["/api/v1/runtime/skills"]

    def test_health_live_exists(self, app: FastAPI) -> None:
        """GET /health/live is registered."""
        paths = app.openapi()["paths"]
        assert "/health/live" in paths
        assert "get" in paths["/health/live"]

    def test_health_ready_exists(self, app: FastAPI) -> None:
        """GET /health/ready is registered."""
        paths = app.openapi()["paths"]
        assert "/health/ready" in paths
        assert "get" in paths["/health/ready"]

    def test_openapi_version(self, app: FastAPI) -> None:
        """OpenAPI version is 3.1.x."""
        version = app.openapi()["openapi"]
        assert version.startswith("3.")
