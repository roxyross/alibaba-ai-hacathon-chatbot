"""Phase 23 Integration Test Suite: Trust, Control, Recovery & AI Reliability Layer.

Validates:
1. Trust Event Recording and Backend-Enforced Verification
2. Reversible Action Rollback vs Non-Reversible Rejection
3. Resilient Recovery Queue, Safe Retries & Idempotency Key Guard
4. Multi-dimensional Trust Metrics (No Fake '94%' Score)
5. Tenant-Isolated User Data Export
6. User Data Deletion and Account Termination with Confirmation
7. Controlled Personalization: Proposal, Approval, and Reset
8. Roxy Health Center: 15-Subsystem Diagnostics and Plain-Language Status
9. Continuous AI Evaluation Dataset & False Completion Prevention
10. Model Intelligence Router: Intent, Complexity, and Permission Preservation
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

sys.path.insert(0, "src")

from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def _get_auth(client: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Helper to request magic link, verify token, and return auth headers + user_id."""
    req_resp = await client.post("/api/v1/auth/request-link", json={"email": email})
    assert req_resp.status_code == 200
    token = req_resp.json()["dev_token"]

    verify_resp = await client.post("/api/v1/auth/verify", json={"token": token})
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    auth_token = data["access_token"]
    user_id = str(data["user"]["id"])
    return {"Authorization": f"Bearer {auth_token}"}, user_id


class TestPhase23TrustAndReliability:
    """End-to-end integration tests for ROXY Trust and Reliability Layer."""

    @pytest.mark.asyncio
    async def test_01_trust_record_and_backend_verification(self, client: httpx.AsyncClient) -> None:
        from app.db import get_db
        from app.trust.service import TrustService

        headers, user_id = await _get_auth(client, f"trust_{uuid.uuid4().hex[:8]}@example.com")

        # Record a reversible action via TrustService directly
        async for db in get_db():
            svc = TrustService(db)
            event = await svc.record_action(
                user_id=user_id,
                action_type="file_move",
                action_name="Move quarterly report to archive",
                risk_level="low",
                permission_policy="allow_automatically",
                rollback_supported=True,
                rollback_strategy="file_restore",
                rollback_payload={"original_path": "/docs/q3.pdf", "destination_path": "/archive/q3.pdf"},
            )
            event_id = event.id
            break

        # List events and check presence
        res = await client.get("/api/v1/trust/events", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        item = next(e for e in data["items"] if e["id"] == event_id)
        assert item["execution_status"] == "requested"
        assert item["verification_status"] == "unverified"

        # Verify via backend-enforced API
        v_res = await client.post(
            f"/api/v1/trust/events/{event_id}/verify",
            headers=headers,
            json={"verified": True, "verification_proof": {"file_exists": True}},
        )
        assert v_res.status_code == 200
        assert v_res.json()["verification_status"] == "verified"
        assert v_res.json()["execution_status"] == "succeeded"

        # Test Rollback of reversible action
        rb_res = await client.post(f"/api/v1/trust/events/{event_id}/rollback", headers=headers)
        assert rb_res.status_code == 200
        assert rb_res.json()["success"] is True
        assert rb_res.json()["rollback_status"] == "rolled_back"


    @pytest.mark.asyncio
    async def test_02_trust_dimensions_no_fake_score(self, client: httpx.AsyncClient) -> None:
        headers, _ = await _get_auth(client, f"dims_{uuid.uuid4().hex[:8]}@example.com")

        res = await client.get("/api/v1/trust/dimensions", headers=headers)
        assert res.status_code == 200
        dims = res.json()

        # Verify concrete dimensions exist and no fake single score
        assert "action_verification" in dims
        assert "source_quality" in dims
        assert "tool_reliability" in dims
        assert "provider_availability" in dims
        assert "permission_compliance" in dims
        assert "execution_confidence" in dims
        assert "trust_score" not in dims, "Must not expose a misleading single decorative trust score"

    @pytest.mark.asyncio
    async def test_03_recovery_jobs_safe_retry_and_idempotency(self, client: httpx.AsyncClient) -> None:
        headers, _ = await _get_auth(client, f"rec_{uuid.uuid4().hex[:8]}@example.com")

        # Non-retryable payment must be rejected
        pay_res = await client.post(
            "/api/v1/trust/recovery-jobs",
            headers=headers,
            json={
                "action_type": "raast_payment",
                "payload": {"amount": 5000, "iban": "PK123"},
                "failure_category": "NETWORK_ERROR",
                "idempotency_key": f"pay_{uuid.uuid4().hex}",
            },
        )
        assert pay_res.status_code == 400
        assert "high-impact" in pay_res.json()["detail"]

        # Safe action enqueued
        idemp_key = f"key_{uuid.uuid4().hex}"
        ok_res = await client.post(
            "/api/v1/trust/recovery-jobs",
            headers=headers,
            json={
                "action_type": "sync_calendar",
                "payload": {"calendar_id": "primary"},
                "failure_category": "CONNECTOR_OFFLINE",
                "idempotency_key": idemp_key,
            },
        )
        assert ok_res.status_code == 200
        job_id = ok_res.json()["id"]

        # Duplicate submission with same idempotency key must return same job
        dup_res = await client.post(
            "/api/v1/trust/recovery-jobs",
            headers=headers,
            json={
                "action_type": "sync_calendar",
                "payload": {"calendar_id": "primary"},
                "failure_category": "CONNECTOR_OFFLINE",
                "idempotency_key": idemp_key,
            },
        )
        assert dup_res.status_code == 200
        assert dup_res.json()["id"] == job_id

        # Trigger retry
        retry_res = await client.post(f"/api/v1/trust/recovery-jobs/{job_id}/retry", headers=headers)
        assert retry_res.status_code == 200
        assert retry_res.json()["status"] == "recovered"

    @pytest.mark.asyncio
    async def test_04_user_data_export_and_tenant_isolation(self, client: httpx.AsyncClient) -> None:
        user1_headers, user1_id = await _get_auth(client, f"u1_{uuid.uuid4().hex[:8]}@example.com")
        user2_headers, user2_id = await _get_auth(client, f"u2_{uuid.uuid4().hex[:8]}@example.com")

        # User 1 requests export
        exp_res = await client.post("/api/v1/account/export", headers=user1_headers)
        assert exp_res.status_code == 200
        job_id = exp_res.json()["job_id"]

        # User 1 downloads export
        dl_res = await client.get(f"/api/v1/account/export/{job_id}", headers=user1_headers)
        assert dl_res.status_code == 200
        payload = dl_res.json()
        assert payload["status"] == "completed"
        assert payload["data"]["user_id"] == user1_id

        # User 2 CANNOT access User 1 export
        unauth_res = await client.get(f"/api/v1/account/export/{job_id}", headers=user2_headers)
        assert unauth_res.status_code == 404

    @pytest.mark.asyncio
    async def test_05_user_data_delete_and_account_cascade(self, client: httpx.AsyncClient) -> None:
        headers, _ = await _get_auth(client, f"del_{uuid.uuid4().hex[:8]}@example.com")

        # Delete personal data
        del_data_res = await client.post("/api/v1/account/delete-data", headers=headers)
        assert del_data_res.status_code == 200
        assert del_data_res.json()["success"] is True
        assert "retention_notice" in del_data_res.json()

        # Delete account with incorrect phrase must fail
        wrong_del = await client.post(
            "/api/v1/account/delete",
            headers=headers,
            json={"confirmation": "PLEASE DELETE"},
        )
        assert wrong_del.status_code == 400

        # Delete account with exact phrase succeeds
        ok_del = await client.post(
            "/api/v1/account/delete",
            headers=headers,
            json={"confirmation": "DELETE MY ACCOUNT"},
        )
        assert ok_del.status_code == 200
        assert ok_del.json()["success"] is True

    @pytest.mark.asyncio
    async def test_06_controlled_personalization_flow(self, client: httpx.AsyncClient) -> None:
        headers, _ = await _get_auth(client, f"pers_{uuid.uuid4().hex[:8]}@example.com")

        # Propose preference
        prop_res = await client.post(
            "/api/v1/personalization/proposals",
            headers=headers,
            json={
                "category": "language",
                "key": "preferred_language",
                "proposed_value": "ur",
                "rationale": "Aap usually Roman Urdu ya Urdu mein baat kartay hain.",
            },
        )
        assert prop_res.status_code == 200
        proposal_id = prop_res.json()["id"]

        # List pending
        list_res = await client.get("/api/v1/personalization/proposals?status=pending", headers=headers)
        assert list_res.status_code == 200
        assert any(p["id"] == proposal_id for p in list_res.json())

        # Approve proposal
        appr_res = await client.post(
            f"/api/v1/personalization/proposals/{proposal_id}/resolve",
            headers=headers,
            json={"approve": True},
        )
        assert appr_res.status_code == 200
        assert appr_res.json()["status"] == "approved"

        # Reset personalization
        reset_res = await client.post("/api/v1/personalization/reset", headers=headers)
        assert reset_res.status_code == 200
        assert reset_res.json()["success"] is True

    @pytest.mark.asyncio
    async def test_07_diagnostics_15_subsystems_health_center(self, client: httpx.AsyncClient) -> None:
        res = await client.get("/api/v1/diagnostics/health-center")
        assert res.status_code == 200
        data = res.json()

        assert data["total_subsystems"] == 15
        names = {s["name"] for s in data["subsystems"]}
        expected_subsystems = {
            "AI Provider",
            "Database",
            "Redis",
            "Memory",
            "Knowledge Vault",
            "Calendar",
            "Email",
            "Device Agent",
            "MCP",
            "Plugins",
            "Workers",
            "Billing",
            "Media Storage",
            "Voice",
            "Research",
        }
        assert names == expected_subsystems
        for s in data["subsystems"]:
            assert s["status"] in (
                "Healthy",
                "Degraded",
                "Unavailable",
                "Needs Reauthentication",
                "Configuration Required",
                "Rate Limited",
                "Offline",
                "Unknown",
            )
            assert s["data_safe"] is True

    @pytest.mark.asyncio
    async def test_08_ai_evaluation_runner_and_false_completion_guard(self, client: httpx.AsyncClient) -> None:
        # Check dataset
        ds_res = await client.get("/api/v1/evaluation/dataset")
        assert ds_res.status_code == 200
        assert ds_res.json()["total_cases"] >= 10

        # Execute evaluation
        run_res = await client.post("/api/v1/evaluation/run")
        assert run_res.status_code == 200
        run_data = run_res.json()
        assert run_data["pass_rate"] == 100.0
        assert run_data["failed"] == 0

        # Check historical runs endpoint
        hist_res = await client.get("/api/v1/evaluation/runs")
        assert hist_res.status_code == 200
        assert len(hist_res.json()) >= 1

    @pytest.mark.asyncio
    async def test_09_model_intelligence_router(self, client: httpx.AsyncClient) -> None:
        headers, _ = await _get_auth(client, f"router_{uuid.uuid4().hex[:8]}@example.com")

        # Test Coding Route
        code_res = await client.post(
            "/api/v1/ai/route-intent",
            headers=headers,
            json={"prompt": "def calculate_risk(portfolio): pass"},
        )
        assert code_res.status_code == 200
        c_data = code_res.json()
        assert c_data["intent"] == "code_generation"
        assert c_data["selected_provider"] == "gemini"
        assert c_data["permission_policy_preserved"] is True

        # Test Image Generation Route
        img_res = await client.post(
            "/api/v1/ai/route-intent",
            headers=headers,
            json={"prompt": "draw a futuristic city at sunset"},
        )
        assert img_res.status_code == 200
        i_data = img_res.json()
        assert i_data["intent"] == "image_generation"
        assert i_data["modality"] == "image"

        # Test Complex Reasoning
        reason_res = await client.post(
            "/api/v1/ai/route-intent",
            headers=headers,
            json={"prompt": "Analyze and compare the financial risk of three different asset allocations over 5 years."},
        )
        assert reason_res.status_code == 200
        r_data = reason_res.json()
        assert r_data["intent"] == "complex_reasoning"
        assert r_data["complexity"] == "high"

    @pytest.mark.asyncio
    async def test_10_usage_intelligence_cost_labeling(self, client: httpx.AsyncClient) -> None:
        headers, _ = await _get_auth(client, f"usage_{uuid.uuid4().hex[:8]}@example.com")

        res = await client.get("/api/v1/usage/stats", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data.get("cost_label") == "Estimated"
        assert "usage_by_feature" in data
        assert "usage_by_model" in data
        assert "timeframe" in data
        assert data["timeframe"]["today"]["cost_label"] == "Estimated"
        assert "ai_models" in data["usage_by_feature"]
        assert "storage" in data["usage_by_feature"]
