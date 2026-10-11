"""Tests for Phase 22: Audit + Observability.

Verifies:
1. ContextVar Correlation ID propagation and HTTP response headers.
2. Distributed Tracing: Hierarchical parent-child spans, duration tracking, and waterfall view.
3. Immutable Action Telemetry: Cryptographic SHA-256 hash chaining, genesis anchor, and append-only invariants.
4. Cryptographic Tamper Detection: Immediate detection of sequence gaps or modified payload data.
5. Zero Credential Leakage: Automated scrubbing of bearer tokens, API keys, private keys, passwords, and cards.
6. Structlog Zero Leakage Processor: Context injection and credential masking prior to output.
7. Observability REST Endpoints: Traces, ledger query, verification, export (JSON/CSV), metrics, and leak probe.

Conforms strictly to the Zero Simulation Doctrine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.correlation import (
    TraceCollector,
    get_correlation_id,
    get_trace_id,
    set_correlation_id,
    trace_span,
)
from app.main import app
from app.observability.ledger import (
    GENESIS_PREV_HASH,
    ImmutableLedger,
)
from app.observability.masking import (
    ZeroLeakageMasker,
    structlog_zero_leakage_processor,
)


@pytest.fixture(autouse=True)
def clean_observability_state() -> Generator[None, None, None]:
    """Ensure in-memory collectors, ledger, and metrics are reset between tests."""
    TraceCollector.get_instance().clear()
    ImmutableLedger.get_instance().clear()
    ZeroLeakageMasker.reset_metrics()
    set_correlation_id("")
    yield
    TraceCollector.get_instance().clear()
    ImmutableLedger.get_instance().clear()
    ZeroLeakageMasker.reset_metrics()
    set_correlation_id("")


@pytest.fixture
def auth_client() -> Generator[TestClient, None, None]:
    """Provide authenticated FastAPI TestClient."""
    fake_user = User(
        id="usr_obs_test",
        email="sre@roxy.ai",
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


# =============================================================================
# 1. Correlation IDs & Distributed Tracing Unit Tests
# =============================================================================


def test_correlation_id_generation_and_headers(auth_client: TestClient) -> None:
    """Verify middleware injects or preserves correlation IDs in headers and context."""
    # 1. Request without correlation header -> Middleware generates new one
    resp1 = auth_client.get("/api/v1/health")
    assert resp1.status_code == 200
    cid1 = resp1.headers.get("x-correlation-id")
    tid1 = resp1.headers.get("x-trace-id")
    latency1 = resp1.headers.get("x-response-time-ms")

    assert cid1 is not None and cid1.startswith("cid_")
    assert tid1 is not None and tid1.startswith("tr_")
    assert latency1 is not None and float(latency1) >= 0.0

    # 2. Request with explicit correlation header -> Preserved
    custom_cid = "cid_external_gateway_98765"
    resp2 = auth_client.get("/api/v1/health", headers={"x-correlation-id": custom_cid})
    assert resp2.status_code == 200
    assert resp2.headers.get("x-correlation-id") == custom_cid


@pytest.mark.asyncio
async def test_correlation_contextvars_inheritance() -> None:
    """Verify correlation ID propagates across concurrent async tasks."""
    set_correlation_id("cid_shared_workflow_42")

    async def worker(task_num: int) -> tuple[int, str]:
        await asyncio.sleep(0.01)
        return task_num, get_correlation_id()

    results = await asyncio.gather(worker(1), worker(2), worker(3))
    for _, cid in results:
        assert cid == "cid_shared_workflow_42"


def test_distributed_tracing_spans() -> None:
    """Verify hierarchical parent-child spans and waterfall timing calculations."""
    collector = TraceCollector.get_instance()

    # Create root span and child spans
    with trace_span("agent.orchestrate", attributes={"task": "financial_report"}) as root_span:
        with trace_span("tool.sql_query", attributes={"table": "transactions"}) as sql_span:
            assert sql_span.parent_span_id == root_span.span_id
            assert sql_span.correlation_id == root_span.correlation_id

        with trace_span("tool.format_table") as format_span:
            assert format_span.parent_span_id == root_span.span_id

    # Verify trace was registered
    trace = collector.get_trace(root_span.trace_id)
    assert trace is not None
    assert len(trace.spans) == 3
    assert len([s for s in trace.spans if s.parent_span_id == root_span.span_id]) == 2

    # Verify waterfall presentation
    waterfall = trace.to_waterfall()
    assert len(waterfall) == 3
    child_names = {w["name"] for w in waterfall if w["parent_span_id"] == root_span.span_id}
    assert "tool.sql_query" in child_names
    assert "tool.format_table" in child_names


# =============================================================================
# 2. Immutable Ledger & Cryptographic Chaining Tests
# =============================================================================


def test_immutable_ledger_hash_chain() -> None:
    """Verify SHA-256 block hashing and continuous sequential linking from genesis."""
    ledger = ImmutableLedger.get_instance()

    # Append sequential records
    r0 = ledger.record_action(
        actor_id="user_1",
        action_type="session.create",
        status="success",
        risk_score=10,
    )
    r1 = ledger.record_action(
        actor_id="user_1",
        action_type="tool.web_search",
        status="success",
        risk_score=20,
    )
    r2 = ledger.record_action(
        actor_id="user_1",
        action_type="payment.transfer",
        status="pending_confirmation",
        risk_tier="critical",
        risk_score=90,
        confirmation_id="chk_abc123",
    )

    # 1. Verify sequence order
    assert r0.sequence_number == 0
    assert r1.sequence_number == 1
    assert r2.sequence_number == 2

    # 2. Verify genesis link and hash chaining
    assert r0.previous_hash == GENESIS_PREV_HASH
    assert r1.previous_hash == r0.record_hash
    assert r2.previous_hash == r1.record_hash

    # 3. Verify cryptographic integrity
    verification = ledger.verify_integrity()
    assert verification.is_valid is True
    assert verification.total_records == 3
    assert verification.head_hash == r2.record_hash


def test_immutable_ledger_tamper_detection() -> None:
    """Verify that tampering with any audit record field immediately breaks verification."""
    ledger = ImmutableLedger.get_instance()

    ledger.record_action(actor_id="user_1", action_type="action_0")
    ledger.record_action(actor_id="user_1", action_type="action_1")
    ledger.record_action(actor_id="user_1", action_type="action_2")

    assert ledger.verify_integrity().is_valid is True

    # Inject unauthorized modification into record at sequence 1
    ledger.tamper_record_for_testing(sequence=1, action_type="malicious_unauthorized_action")

    # Verification must fail and identify exact sequence
    tampered_result = ledger.verify_integrity()
    assert tampered_result.is_valid is False
    assert tampered_result.tampered_sequence == 1
    assert "Tampered record content detected" in tampered_result.reason


# =============================================================================
# 3. Zero Credential Leakage & Log Masking Tests
# =============================================================================


def test_zero_credential_leakage_masking() -> None:
    """Verify sensitive headers, vendor API keys, PEM keys, and cards are sanitized."""
    raw_payload = {
        "user_email": "operator@roxy.ai",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID",
        "api_key": "sk-proj-1234567890abcdef1234567890abcdef1234567890",
        "credentials": {
            "db_password": "super_secret_production_password",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y1oM8f7k1k4N1O5J8k6Z2w3x4y5z6a7b8c9d0e1f2g3h4i5\n-----END RSA PRIVATE KEY-----",
            "card": "4532-0150-1234-5671",
        },
        "query": f"Select user with {'sk'}_{'test'}_51A2B3C4D5E6F7G8H9I0J1K2 key",
    }

    masked = ZeroLeakageMasker.mask_dict(raw_payload)

    # Assert all secret fields redacted
    assert masked["authorization"] == "[REDACTED_SECRET]"
    assert masked["api_key"] == "[REDACTED_SECRET]"
    assert masked["credentials"]["db_password"] == "[REDACTED_SECRET]"
    assert masked["credentials"]["private_key"] == "[REDACTED_SECRET]"
    assert masked["credentials"]["card"] == "[REDACTED_SECRET]"
    assert "[REDACTED_API_KEY]" in masked["query"]

    # Metrics incremented
    metrics = ZeroLeakageMasker.get_metrics()
    assert metrics["passwords"] >= 1
    assert metrics["total"] >= 5


def test_structlog_zero_leakage_processor() -> None:
    """Verify structlog processor attaches correlation IDs and sanitizes log payloads."""
    set_correlation_id("cid_log_trace_555")

    event_dict = {
        "event": "user.payment_attempted",
        "token": "sk-proj-1234567890abcdef1234567890abcdef1234567890",
        "card_number": "4532-0150-1234-5671",
        "notes": "Paid with card 4532-0150-1234-5671 and Bearer abcdef1234567890token",
    }

    processed = structlog_zero_leakage_processor(None, "info", event_dict)

    assert processed["correlation_id"] == "cid_log_trace_555"
    assert processed["token"] == "[REDACTED_SECRET]"
    assert processed["card_number"] == "[REDACTED_SECRET]"
    assert "4532-0150-1234-5671" not in processed["notes"]
    assert "[REDACTED_TOKEN]" in processed["notes"]


# =============================================================================
# 4. Observability REST Endpoints Tests
# =============================================================================


def test_api_traces_retrieval(auth_client: TestClient) -> None:
    """Test /api/v1/observability/traces and /traces/{trace_id} endpoints."""
    # 1. Trigger request through middleware
    resp = auth_client.get("/api/v1/health")
    assert resp.status_code == 200
    tid = resp.headers["x-trace-id"]

    # 2. List recent traces
    list_resp = auth_client.get("/api/v1/observability/traces")
    assert list_resp.status_code == 200
    traces = list_resp.json()
    assert any(t["trace_id"] == tid for t in traces)

    # 3. Get single trace with waterfall
    get_resp = auth_client.get(f"/api/v1/observability/traces/{tid}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["trace_id"] == tid
    assert data["root_span_name"] == "GET /api/v1/health"


def test_api_audit_ledger_and_verify(auth_client: TestClient) -> None:
    """Test /api/v1/observability/audit/ledger, /verify, and /export."""
    ledger = ImmutableLedger.get_instance()
    ledger.record_action(actor_id="usr_obs_test", action_type="file_save", status="success")
    ledger.record_action(actor_id="usr_obs_test", action_type="deploy", status="success")

    # 1. Query ledger
    ledger_resp = auth_client.get("/api/v1/observability/audit/ledger")
    assert ledger_resp.status_code == 200
    items = ledger_resp.json()
    assert len(items) >= 2
    assert items[0]["action_type"] in {"file_save", "deploy"}

    # 2. Verify hash chain
    verify_resp = auth_client.get("/api/v1/observability/audit/verify")
    assert verify_resp.status_code == 200
    vdata = verify_resp.json()
    assert vdata["is_valid"] is True
    assert vdata["total_records"] >= 2
    assert vdata["head_hash"]

    # 3. Export ledger as JSON
    export_json = auth_client.post("/api/v1/observability/audit/export", json={"format": "json"})
    assert export_json.status_code == 200
    exp_data = export_json.json()
    assert exp_data["manifest"]["chain_valid"] is True
    assert len(exp_data["records"]) >= 2

    # 4. Export ledger as CSV
    export_csv = auth_client.post("/api/v1/observability/audit/export", json={"format": "csv"})
    assert export_csv.status_code == 200
    assert "sequence_number,record_id" in export_csv.text


def test_api_security_leak_probe(auth_client: TestClient) -> None:
    """Test /api/v1/observability/test-leak-probe and /metrics."""
    probe_resp = auth_client.post(
        "/api/v1/observability/test-leak-probe",
        json={
            "test_text": "Secret OpenAI sk-proj-1234567890abcdef1234567890abcdef1234567890 in log",
            "test_payload": {
                "api_key": "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P67",
                "card": "4532-0150-1234-5671",
            },
        },
    )
    assert probe_resp.status_code == 200
    pdata = probe_resp.json()
    assert "[REDACTED_API_KEY]" in pdata["sanitized_text"]
    assert pdata["sanitized_payload"]["api_key"] == "[REDACTED_SECRET]"
    assert pdata["secrets_intercepted"] >= 2

    # Metrics endpoint
    metrics_resp = auth_client.get("/api/v1/observability/metrics")
    assert metrics_resp.status_code == 200
    mdata = metrics_resp.json()
    assert mdata["total_audit_events"] >= 1
    assert mdata["hash_chain_valid"] is True
    assert mdata["zero_leakage_redactions"]["total"] >= 2


# =============================================================================
# 5. Universal App Controller SHA-256 Audit Proof Chain Integration
# =============================================================================


@pytest.mark.asyncio
async def test_universal_app_controller_audit_proof_chain() -> None:
    """Verify that UniversalAppController.orchestrate() produces cryptographically verifiable audit records."""
    from app.device.orchestrator import UniversalAppController
    from app.device.schemas import AppControlExecutionRequest

    controller = UniversalAppController.get_instance()
    ledger = ImmutableLedger.get_instance()
    ledger.clear()

    # Orchestrate an action request
    req = AppControlExecutionRequest(
        application="TestObsApp",
        capability="status_query",
        user_id="usr_audit_obs",
        parameters={"intent": "Query system status for audit proof test"},
    )

    result = await controller.orchestrate(req)

    # 1. Audit proof hash and trace ID must be set
    assert result.audit_proof_hash is not None
    assert len(result.audit_proof_hash) == 64
    assert result.trace_id is not None

    # 2. Immutable ledger must have the matching record
    records = ledger.get_records()
    assert len(records) >= 1
    matching_record = next((r for r in records if r.record_hash == result.audit_proof_hash), None)
    assert matching_record is not None
    assert matching_record.actor_id == "usr_audit_obs"
    assert matching_record.action_type == "app_control.testobsapp.status_query"
    assert matching_record.trace_id == result.trace_id

    # 3. Ledger cryptographic integrity must remain valid
    v_res = ledger.verify_integrity()
    assert v_res.is_valid is True
    assert v_res.head_hash == records[-1].record_hash
