"""ROXY JARVIS AI Gateway — FastAPI application entry point."""

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load .env from the working directory (or backend/.env if cwd is the repo
# root) so `python -m app.main` works without `set -a; source .env; set +a`.
# Existing shell env vars take precedence (`override=False` is the default).
_backend_env = Path(__file__).resolve().parents[2] / ".env"
if _backend_env.exists():
    load_dotenv(_backend_env, override=False)
elif Path(".env").exists():
    load_dotenv(".env", override=False)

# structlog is configured in `app/__init__.py` so it runs before any
# module-level `structlog.get_logger()` call anywhere under `app.*`.

from app.api.v1.ai import router as ai_router
from app.api.v1.bank import router as bank_router
from app.api.v1.billing import router as billing_router
from app.api.v1.calendar import router as calendar_router
from app.api.v1.documents import router as documents_router
from app.api.v1.emails import router as emails_router
from app.api.v1.finance import router as finance_router
from app.api.v1.greeting import router as greeting_router
from app.api.v1.images import router as images_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.projects import router as projects_router
from app.api.v1.raast import router as raast_router
from app.api.v1.runtime import router as runtime_router
from app.api.v1.usage import router as usage_router
from app.api.v1.voice import router as voice_router
from app.api.v1.research import router as research_router
from app.api.v1.browser import router as browser_router
from app.api.v1.study import router as study_router
from app.api.v1.coding import router as coding_router
from app.api.v1.reminders import router as reminders_router
from app.api.v1.memory import router as memory_router
from app.api.v1.audit import router as audit_router
from app.media.router import router as media_router
from app.auth.router import router as auth_router
from app.chat_history.router import router as chat_history_router
from app.model_provider.router import router as model_provider_router
from app.providers.router import router as providers_router
from app.session.router import router as session_router
from app.settings.router import router as settings_router
from app.skills.router import router as skills_router
from app.permissions.router import router as permissions_router
from app.actions.router import router as actions_router
from app.agent_runtime.router import router as agents_router, tools_router
from app.connectors.router import router as connectors_router
from app.device.router import router as device_router
from app.mcp.router import router as mcp_router
from app.tools.builtin import register_builtin_tools
from app.vault.router import router as vault_router
from app.artifacts.router import router as artifacts_router
from app.trust.router import router as trust_router
from app.account.router import router as account_router
from app.personalization.router import router as personalization_router
from app.diagnostics.router import router as diagnostics_router
from app.evaluation.router import router as evaluation_router
from app.observability.router import router as observability_router
from app.testing_matrix.router import testing_matrix_router
from app.adversarial_security.router import router as adversarial_security_router
from app.production_readiness.router import router as production_readiness_router
from app.open_work.router import router as open_work_router
from app.plugins.router import router as plugins_router
from app.core.middleware import CorrelationMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="ROXY JARVIS AI Gateway",
    description="Multi-provider AI abstraction layer with routing, failover, and attribution.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend to call the gateway
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
_allowed_origins = list(dict.fromkeys(_default_origins + _extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app|https://.*\.roxy\.ai)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationMiddleware)

@app.get("/api/v1/health")
@app.get("/health")
@app.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """Process liveness probe."""
    return {
        "status": "ok",
        "service": "roxy-ai-gateway",
        "version": os.environ.get("ROXY_VERSION", "2.0.0"),
        "commit_sha": os.environ.get("COMMIT_SHA", os.environ.get("GIT_SHA", "unknown")),
        "environment": os.environ.get("APP_ENV", "development"),
    }


@app.get("/health/ready")
async def readiness_check() -> JSONResponse:
    """Readiness probe checking database connectivity and critical configuration."""
    db_ok = True
    db_msg = "configured"
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        try:
            from sqlalchemy import text
            from app.db import get_engine
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_msg = "healthy"
        except Exception as exc:
            db_ok = False
            db_msg = "unreachable"
            import structlog
            structlog.get_logger().warning("health.db_readiness_failed", error=str(exc))
    else:
        db_msg = "not_configured"

    # In production, database is mandatory for serving traffic
    is_prod = os.environ.get("APP_ENV", "").lower() in ("production", "prod") or os.environ.get("ENVIRONMENT", "").lower() in ("production", "prod")
    if is_prod and not db_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "service": "roxy-ai-gateway",
                "database": db_msg,
                "environment": os.environ.get("APP_ENV", "production"),
            },
        )

    # Optional AI providers without keys do NOT fail readiness
    return JSONResponse(
        status_code=200 if db_ok else 200,
        content={
            "status": "ready" if db_ok else "degraded",
            "service": "roxy-ai-gateway",
            "database": db_msg,
            "version": os.environ.get("ROXY_VERSION", "2.0.0"),
            "environment": os.environ.get("APP_ENV", "development"),
        },
    )


@app.get("/system-health")
@app.get("/api/health")
@app.get("/api/health/system")
@app.get("/api/v1/system-health")
async def system_health_check() -> dict[str, Any]:
    """Phase K: Roxy Health Center diagnostic probing across 22 subsystems."""
    from app.diagnostics.service import DiagnosticsService
    svc = DiagnosticsService(db=None)
    return await svc.get_system_health()

# Register all routes under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(model_provider_router, prefix="/api/v1")
app.include_router(providers_router, prefix="/api/v1")
app.include_router(session_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(chat_history_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(skills_router, prefix="/api/v1")
app.include_router(bank_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(runtime_router, prefix="/api/v1")
app.include_router(finance_router, prefix="/api/v1")
app.include_router(greeting_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")
app.include_router(usage_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(images_router, prefix="/api/v1")
app.include_router(raast_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(calendar_router, prefix="/api/v1")
app.include_router(emails_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(browser_router, prefix="/api/v1")
app.include_router(study_router, prefix="/api/v1")
app.include_router(coding_router, prefix="/api/v1")
app.include_router(reminders_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(media_router, prefix="/api/v1")
app.include_router(permissions_router, prefix="/api/v1")
app.include_router(actions_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(tools_router, prefix="/api/v1")
app.include_router(connectors_router, prefix="/api/v1")
app.include_router(mcp_router, prefix="/api/v1")
app.include_router(device_router, prefix="/api/v1")
app.include_router(vault_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")
app.include_router(trust_router, prefix="/api/v1")
app.include_router(account_router, prefix="/api/v1")
app.include_router(personalization_router, prefix="/api/v1")
app.include_router(diagnostics_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")
app.include_router(observability_router, prefix="/api/v1")
app.include_router(testing_matrix_router, prefix="/api/v1")
app.include_router(adversarial_security_router, prefix="/api/v1")
app.include_router(production_readiness_router, prefix="/api/v1")

# Unversioned aliases for device and trust services
app.include_router(device_router, prefix="/api")
app.include_router(trust_router, prefix="/api")
app.include_router(open_work_router, prefix="/api/v1")
app.include_router(plugins_router, prefix="/api/v1")

_static_dir = Path(__file__).resolve().parents[2] / "static"
try:
    _static_dir.mkdir(parents=True, exist_ok=True)
except OSError:
    import tempfile
    _static_dir = Path(tempfile.gettempdir()) / "roxy_static"
    try:
        _static_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    """Start the APScheduler job runner and ensure DB tables exist."""
    # Enforce P0 production billing configuration gate before accepting traffic or operations
    from app.billing.validator import validate_billing_configuration
    validate_billing_configuration()

    # Ensure all ORM models are registered before creating tables
    try:
        import app.auth.models  # noqa: F401
        import app.chat_history.models  # noqa: F401
        import app.models.agent_runtime  # noqa: F401
        import app.models.audit_log  # noqa: F401
        import app.models.bank_connection  # noqa: F401
        import app.models.browser_task  # noqa: F401
        import app.models.budget  # noqa: F401
        import app.models.calendar_event  # noqa: F401
        import app.models.code_snippet  # noqa: F401
        import app.models.connector  # noqa: F401
        import app.models.custom_skill  # noqa: F401
        import app.models.device  # noqa: F401
        import app.models.document_vault  # noqa: F401
        import app.models.email_message  # noqa: F401
        import app.models.finance_account  # noqa: F401
        import app.models.generated_image  # noqa: F401
        import app.models.mcp  # noqa: F401
        import app.models.media_job  # noqa: F401
        import app.models.model  # noqa: F401
        import app.models.project  # noqa: F401
        import app.models.provider  # noqa: F401
        import app.models.research_report  # noqa: F401
        import app.models.scheduled_job  # noqa: F401
        import app.models.semantic_memory  # noqa: F401
        import app.models.spending_alert  # noqa: F401
        import app.models.study_deck  # noqa: F401
        import app.models.subscription  # noqa: F401
        import app.models.token_usage  # noqa: F401
        import app.models.user_preference  # noqa: F401
        import app.models.voice_recording  # noqa: F401
        import app.session.models  # noqa: F401
        from app.db import Base, get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        import structlog
        structlog.get_logger().warning("db.init_tables_failed", error=str(exc))

    try:
        from app.job_scheduler import start_scheduler
        start_scheduler()
    except Exception as exc:
        import structlog
        structlog.get_logger().warning("job_scheduler.startup_failed", error=str(exc))

    try:
        from app.trust.confirmation_gate import ConfirmationGate
        ConfirmationGate._load_from_disk()
    except Exception as exc:
        import structlog
        structlog.get_logger().warning("confirmation_gate.startup_load_failed", error=str(exc))

    try:
        register_builtin_tools()
        from app.device.service import DeviceService
        DeviceService.get_instance().register_device_tools()
        from app.research.service import ResearchService
        ResearchService.get_instance().register_research_tools()
        from app.browser.service import BrowserService
        BrowserService.get_instance().register_browser_tools()
        from app.billing.service import PaymentService
        PaymentService.get_instance().register_billing_tools()
        from app.projects.service import ProjectService
        ProjectService.get_instance().register_workspace_tools()
        from app.images.service import ImageStudioService
        ImageStudioService.get_instance().register_image_tools()
        from app.calendar.service import CalendarService
        CalendarService.get_instance().register_calendar_tools()
        from app.artifacts.service import CoworkService
        CoworkService.get_instance().register_cowork_tools()
        from app.jobs.service import JobService
        JobService.get_instance().register_scheduler_tools()
        from app.finance.service import FinanceService
        FinanceService.get_instance().register_finance_tools()
        from app.study.service import StudyService
        StudyService.get_instance().register_tutor_tools()
        from app.files.service import FileSystemService
        FileSystemService.get_instance().register_file_tools()
    except Exception as exc:
        import structlog
        structlog.get_logger().warning("builtin_tools.startup_failed", error=str(exc))



@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Stop the APScheduler job runner when the backend stops."""
    from app.job_scheduler import stop_scheduler
    stop_scheduler()


# Email send alias route so both /api/v1/email/send and /api/v1/skills/email_send work
@app.post("/api/v1/email/send")
async def email_send_alias(
    req: dict[str, Any],
) -> Any:
    from app.skills.email_send import get_executor
    from app.skills.schemas import EmailSendRequest

    to = str(req.get("to", ""))
    subject = str(req.get("subject", ""))
    body = str(req.get("body", ""))
    cc = req.get("cc", [])
    bcc = req.get("bcc", [])

    model_req = EmailSendRequest(
        to=to,
        subject=subject,
        body=body,
        cc=cc if isinstance(cc, list) else [],
        bcc=bcc if isinstance(bcc, list) else [],
        confirm=True,
    )
    executor = get_executor()
    result = await executor.execute(model_req)
    return result



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
