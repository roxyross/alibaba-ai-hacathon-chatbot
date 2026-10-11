"""Tests for Phase 16: App Embedding & In-Roxy Workspace.

Verifies:
1. URL safety sanitization & SSRF protection against cloud metadata and dangerous schemes.
2. Embedding security header evaluation (direct iframe vs. sandboxed proxy).
3. Frame-ancestors and X-Frame-Options header handling.
4. Workspace surface session lifecycle (create, get, heartbeat, resize, list, terminate).
5. Desktop projection window targeting and live frame capture.
6. Canvas-to-window coordinate transformation and input relay.
7. Safe reverse proxy header stripping and workspace security injection.
8. Central ToolRegistry dynamic workspace tools invocation.
9. FastAPI REST endpoints for evaluation, sessions, streaming, input, and proxy.

Conforms strictly to the Zero Simulation Doctrine.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Generator

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.schemas import (
    CreateSurfaceSessionRequest,
    EmbeddingSurfaceType,
    EmbedSecurityVerdict,
    RelayInputRequest,
    WorkspaceSessionStatus,
)
from app.device.service import DeviceService
from app.device.workspace_embedding import (
    EmbedSecurityEvaluator,
    SafeEmbeddingReverseProxy,
    get_workspace_surface_manager,
)
from app.main import app
from app.tools.registry import ToolRegistry

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_workspace_state() -> Generator[None, None, None]:
    """Ensure in-memory surface sessions and tools are reset between test runs."""
    mgr = get_workspace_surface_manager()
    # Reset sessions
    mgr._sessions.clear()
    svc = DeviceService.get_instance()
    svc.clear_in_memory_state()
    yield
    mgr._sessions.clear()


@pytest.fixture
def mock_user() -> User:
    return User(
        id="usr_phase16_test_001",
        email="test_phase16@roxy.ai",
    )


@pytest.fixture
def auth_client(mock_user: User) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


# -----------------------------------------------------------------------------
# 1. URL Safety & SSRF Sanitization
# -----------------------------------------------------------------------------

def test_url_safety_and_ssrf_sanitization() -> None:
    """Verify dangerous schemes and cloud metadata IPs are strictly rejected."""
    # Forbidden schemes
    dangerous_urls = [
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "file:///etc/passwd",
        "file:///C:/Windows/win.ini",
        "blob:http://example.com/uuid",
        "vbscript:msgbox(1)",
    ]
    for bad_url in dangerous_urls:
        is_safe, _, reason = EmbedSecurityEvaluator.sanitize_url(bad_url)
        assert not is_safe, f"Expected {bad_url} to be unsafe"
        assert "Forbidden" in reason or "Unsupported" in reason

    # Cloud metadata endpoints
    metadata_urls = [
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://100.100.100.200/latest/meta-data/",
    ]
    for meta_url in metadata_urls:
        is_safe, _, reason = EmbedSecurityEvaluator.sanitize_url(meta_url)
        assert not is_safe, f"Expected {meta_url} to be blocked"
        assert "metadata" in reason.lower()

    # Valid URLs
    valid_urls = [
        "https://github.com",
        "https://notion.so/my-workspace",
        "http://localhost:3000",
        "http://127.0.0.1:8000/docs",
    ]
    for good_url in valid_urls:
        is_safe, clean_url, _ = EmbedSecurityEvaluator.sanitize_url(good_url)
        assert is_safe, f"Expected {good_url} to be safe"
        assert clean_url.startswith("http")


# -----------------------------------------------------------------------------
# 2. Embed Security Header Evaluation (Direct vs Proxy vs Blocked)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_security_header_evaluation_direct() -> None:
    """Verify that sites without frame restrictions receive an ALLOWED_DIRECT verdict."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/html",
                "Server": "TestServer/1.0",
            },
            text="<html><body>Hello Roxy Workspace</body></html>",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await EmbedSecurityEvaluator.evaluate_url(
            url="https://embed-friendly-app.com",
            allow_proxy=True,
            custom_client=client,
        )
        assert res.is_embeddable is True
        assert res.verdict == EmbedSecurityVerdict.ALLOWED_DIRECT
        assert res.recommended_surface == EmbeddingSurfaceType.DIRECT_IFRAME
        assert "allow-scripts" in res.sandbox_attributes
        assert "camera 'none'" in res.permissions_policy
        assert res.proxy_url is None


@pytest.mark.asyncio
async def test_embed_security_header_evaluation_xfo_deny() -> None:
    """Verify that X-Frame-Options: DENY triggers REQUIRES_PROXY when proxy is enabled."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/html",
                "X-Frame-Options": "DENY",
            },
            text="<html><body>Protected Portal</body></html>",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # Case 1: allow_proxy = True -> REQUIRES_PROXY
        res_proxy = await EmbedSecurityEvaluator.evaluate_url(
            url="https://protected-site.com",
            allow_proxy=True,
            custom_client=client,
        )
        assert res_proxy.is_embeddable is True
        assert res_proxy.verdict == EmbedSecurityVerdict.REQUIRES_PROXY
        assert res_proxy.recommended_surface == EmbeddingSurfaceType.SANDBOXED_PROXY
        assert res_proxy.x_frame_options == "DENY"
        assert res_proxy.proxy_url is not None
        assert "/embedding/proxy?url=" in res_proxy.proxy_url

        # Case 2: allow_proxy = False -> BLOCKED_UNSAFE
        res_blocked = await EmbedSecurityEvaluator.evaluate_url(
            url="https://protected-site.com",
            allow_proxy=False,
            custom_client=client,
        )
        assert res_blocked.is_embeddable is False
        assert res_blocked.verdict == EmbedSecurityVerdict.BLOCKED_UNSAFE
        assert res_blocked.proxy_url is None


@pytest.mark.asyncio
async def test_embed_security_header_evaluation_csp_frame_ancestors() -> None:
    """Verify that CSP frame-ancestors 'none' triggers REQUIRES_PROXY."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/html",
                "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
            },
            text="<html><body>Secure Dashboard</body></html>",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await EmbedSecurityEvaluator.evaluate_url(
            url="https://csp-protected.com",
            allow_proxy=True,
            custom_client=client,
        )
        assert res.is_embeddable is True
        assert res.verdict == EmbedSecurityVerdict.REQUIRES_PROXY
        assert res.csp_frame_ancestors == "frame-ancestors 'none'"
        assert res.recommended_surface == EmbeddingSurfaceType.SANDBOXED_PROXY


# -----------------------------------------------------------------------------
# 3. Workspace Surface Session Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workspace_session_lifecycle() -> None:
    """Verify end-to-end surface session creation, heartbeat, resize, list, and termination."""
    mgr = get_workspace_surface_manager()

    # 1. Create a desktop projection session
    req = CreateSurfaceSessionRequest(
        app_name="Visual Studio Code",
        device_id="desktop_dev_01",
        surface_type=EmbeddingSurfaceType.DESKTOP_PROJECTION,
        viewport_width=1280,
        viewport_height=800,
        preferred_fps=30,
        metadata={"category": "development"},
    )
    session = await mgr.create_session(req)
    assert session.session_id is not None
    assert session.status == WorkspaceSessionStatus.ACTIVE
    assert session.viewport_width == 1280
    assert session.viewport_height == 800
    assert session.auth_token is not None

    # 2. Retrieve session
    fetched = await mgr.get_session(session.session_id)
    assert fetched is not None
    assert fetched.app_name == "Visual Studio Code"

    # 3. Heartbeat
    initial_hb = session.last_heartbeat
    hb_session = await mgr.heartbeat(session.session_id)
    assert hb_session.last_heartbeat >= initial_hb

    # 4. Resize Viewport
    resized = await mgr.resize_viewport(session.session_id, width=1920, height=1080)
    assert resized.viewport_width == 1920
    assert resized.viewport_height == 1080

    # 5. List sessions
    all_sessions = await mgr.list_sessions(device_id="desktop_dev_01")
    assert len(all_sessions) == 1
    assert all_sessions[0].session_id == session.session_id

    # 6. Terminate session
    terminated = await mgr.terminate_session(session.session_id)
    assert terminated is True

    # 7. Post-termination verification
    post_check = await mgr.get_session(session.session_id)
    assert post_check is None or post_check.status == WorkspaceSessionStatus.TERMINATED


# -----------------------------------------------------------------------------
# 4. Desktop Projection Window Targeting & Live Frame Capture
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_projection_frame_capture() -> None:
    """Verify live frame capture produces valid, decodable JPEG image buffers."""
    mgr = get_workspace_surface_manager()

    session = await mgr.create_session(
        CreateSurfaceSessionRequest(
            app_name="Notepad",
            viewport_width=800,
            viewport_height=600,
            preferred_fps=20,
        )
    )

    frame = await mgr.capture_frame(session.session_id)
    assert frame.session_id == session.session_id
    assert frame.frame_number >= 1
    assert frame.width == 800
    assert frame.height == 600
    assert frame.format == "image/jpeg"
    assert frame.data_base64 is not None

    # Decode and verify authentic image content
    raw_bytes = base64.b64decode(frame.data_base64)
    assert len(raw_bytes) > 100
    image = Image.open(io.BytesIO(raw_bytes))
    assert image.format == "JPEG"
    assert image.size == (800, 600)


# -----------------------------------------------------------------------------
# 5. Input Relay & Coordinate Transformation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_desktop_projection_input_relay() -> None:
    """Verify canvas coordinates are properly transformed and dispatched to desktop automation."""
    mgr = get_workspace_surface_manager()

    session = await mgr.create_session(
        CreateSurfaceSessionRequest(
            app_name="Calculator",
            viewport_width=1000,
            viewport_height=800,
        )
    )

    # 1. Click Relay
    click_res = await mgr.relay_input(
        session.session_id,
        RelayInputRequest(
            session_id=session.session_id,
            action="click",
            x=500,
            y=400,
            button="left",
        ),
    )
    assert click_res.success is True
    assert click_res.action == "click"
    assert click_res.details["canvas_coords"]["x"] == 500
    assert click_res.details["canvas_coords"]["y"] == 400

    # 2. Text Typing Relay
    type_res = await mgr.relay_input(
        session.session_id,
        RelayInputRequest(
            session_id=session.session_id,
            action="type_text",
            text="42 + 58 = ",
        ),
    )
    assert type_res.success is True
    assert type_res.action == "type_text"

    # 3. Hotkey Relay
    hotkey_res = await mgr.relay_input(
        session.session_id,
        RelayInputRequest(
            session_id=session.session_id,
            action="hotkey",
            hotkey="ctrl+c",
        ),
    )
    assert hotkey_res.success is True
    assert hotkey_res.action == "hotkey"

    # 4. Scroll Relay
    scroll_res = await mgr.relay_input(
        session.session_id,
        RelayInputRequest(
            session_id=session.session_id,
            action="scroll",
            delta_y=150,
        ),
    )
    assert scroll_res.success is True
    assert scroll_res.action == "scroll"


# -----------------------------------------------------------------------------
# 6. Safe Sandboxed Reverse Proxy
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_reverse_proxy_behavior() -> None:
    """Verify the reverse proxy strips hostile frame-busting headers and injects isolation policies."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "frame-ancestors 'none'",
                "Strict-Transport-Security": "max-age=31536000",
                "X-Custom-App": "MyInternalApp",
            },
            text="<html><body>Internal Enterprise Portal</body></html>",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        status_code, headers, body = await SafeEmbeddingReverseProxy.proxy_request(
            target_url="https://internal-app.example.com",
            custom_client=client,
        )

        assert status_code == 200
        # Verify hostile headers stripped
        assert "x-frame-options" not in headers
        assert "strict-transport-security" not in headers
        # Verify proxy headers injected
        assert headers.get("X-Roxy-Proxied") == "true"
        assert "frame-ancestors 'self'" in headers.get("Content-Security-Policy", "")
        assert "X-Content-Type-Options" in headers
        assert b"Internal Enterprise Portal" in body


# -----------------------------------------------------------------------------
# 7. DeviceService ToolRegistry Workspace Tools Execution
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_service_workspace_tools() -> None:
    """Verify all 5 Phase 16 agent tools are properly registered and executable via ToolRegistry."""
    registry = ToolRegistry.get_instance()

    # Tool 1: workspace_evaluate_embed
    tool_eval = registry.get("workspace_evaluate_embed")
    assert tool_eval is not None
    handler_eval = registry.get_handler("workspace_evaluate_embed")
    assert handler_eval is not None
    res_eval = await handler_eval(url="https://example.com", allow_proxy=True)
    assert "verdict" in res_eval
    assert "is_embeddable" in res_eval

    # Tool 2: workspace_create_surface_session
    tool_create = registry.get("workspace_create_surface_session")
    assert tool_create is not None
    handler_create = registry.get_handler("workspace_create_surface_session")
    assert handler_create is not None
    res_session = await handler_create(
        app_name="Slack Desktop",
        surface_type="desktop_projection",
        viewport_width=1280,
        viewport_height=720,
    )
    session_id = res_session["session_id"]
    assert session_id is not None
    assert res_session["status"] == "active"

    # Tool 3: workspace_capture_window_frame
    tool_frame = registry.get("workspace_capture_window_frame")
    assert tool_frame is not None
    handler_frame = registry.get_handler("workspace_capture_window_frame")
    assert handler_frame is not None
    res_frame = await handler_frame(session_id=session_id)
    assert res_frame["session_id"] == session_id
    assert "data_base64" in res_frame

    # Tool 4: workspace_relay_input
    tool_input = registry.get("workspace_relay_input")
    assert tool_input is not None
    handler_input = registry.get_handler("workspace_relay_input")
    assert handler_input is not None
    res_input = await handler_input(
        session_id=session_id,
        action="click",
        x=300,
        y=200,
    )
    assert res_input["success"] is True

    # Tool 5: workspace_terminate_surface_session
    tool_term = registry.get("workspace_terminate_surface_session")
    assert tool_term is not None
    handler_term = registry.get_handler("workspace_terminate_surface_session")
    assert handler_term is not None
    res_term = await handler_term(session_id=session_id)
    assert res_term["terminated"] is True


# -----------------------------------------------------------------------------
# 8. FastAPI Workspace Embedding Endpoints
# -----------------------------------------------------------------------------

def test_api_workspace_embedding_endpoints(auth_client: TestClient) -> None:
    """Verify all FastAPI REST endpoints for Phase 16 app embedding and projection."""
    device_id = "test_dev_p16"

    # 1. POST /api/v1/devices/{device_id}/embedding/evaluate
    eval_resp = auth_client.post(
        f"/api/v1/devices/{device_id}/embedding/evaluate",
        json={"url": "https://example.com", "allow_proxy": True},
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["url"] == "https://example.com"
    assert "verdict" in eval_data
    assert "is_embeddable" in eval_data

    # 2. POST /api/v1/devices/{device_id}/embedding/sessions
    sess_resp = auth_client.post(
        f"/api/v1/devices/{device_id}/embedding/sessions",
        json={
            "app_name": "Terminal",
            "surface_type": "desktop_projection",
            "viewport_width": 1024,
            "viewport_height": 768,
        },
    )
    assert sess_resp.status_code == 200
    sess_data = sess_resp.json()
    session_id = sess_data["session_id"]
    assert session_id is not None
    assert sess_data["status"] == "active"

    # 3. GET /api/v1/devices/{device_id}/embedding/sessions
    list_resp = auth_client.get(f"/api/v1/devices/{device_id}/embedding/sessions")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total_sessions"] >= 1
    assert any(s["session_id"] == session_id for s in list_data["sessions"])

    # 4. GET /api/v1/devices/{device_id}/embedding/sessions/{session_id}
    get_resp = auth_client.get(f"/api/v1/devices/{device_id}/embedding/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["app_name"] == "Terminal"

    # 5. POST /api/v1/devices/{device_id}/embedding/sessions/{session_id}/heartbeat
    hb_resp = auth_client.post(f"/api/v1/devices/{device_id}/embedding/sessions/{session_id}/heartbeat")
    assert hb_resp.status_code == 200
    assert hb_resp.json()["status"] == "active"

    # 6. POST /api/v1/devices/{device_id}/embedding/sessions/{session_id}/resize
    resize_resp = auth_client.post(
        f"/api/v1/devices/{device_id}/embedding/sessions/{session_id}/resize?width=1600&height=900"
    )
    assert resize_resp.status_code == 200
    assert resize_resp.json()["viewport_width"] == 1600
    assert resize_resp.json()["viewport_height"] == 900

    # 7. GET /api/v1/devices/{device_id}/embedding/sessions/{session_id}/frame
    frame_resp = auth_client.get(f"/api/v1/devices/{device_id}/embedding/sessions/{session_id}/frame")
    assert frame_resp.status_code == 200
    frame_data = frame_resp.json()
    assert frame_data["session_id"] == session_id
    assert "data_base64" in frame_data

    # 8. POST /api/v1/devices/{device_id}/embedding/sessions/{session_id}/input
    input_resp = auth_client.post(
        f"/api/v1/devices/{device_id}/embedding/sessions/{session_id}/input",
        json={
            "session_id": session_id,
            "action": "click",
            "x": 250,
            "y": 150,
        },
    )
    assert input_resp.status_code == 200
    assert input_resp.json()["success"] is True

    # 9. GET /api/v1/devices/{device_id}/embedding/proxy
    proxy_resp = auth_client.get(
        f"/api/v1/devices/{device_id}/embedding/proxy",
        params={"url": "https://example.com"},
    )
    # Target may be online or offline; proxy handles either cleanly
    assert proxy_resp.status_code in (200, 502)

    # 10. DELETE /api/v1/devices/{device_id}/embedding/sessions/{session_id}
    del_resp = auth_client.delete(f"/api/v1/devices/{device_id}/embedding/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["terminated"] is True
