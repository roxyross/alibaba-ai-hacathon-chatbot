"""ROXY JARVIS AI Gateway — FastAPI application entry point."""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import Request as StarletteRequest
from fastapi.middleware.cors import CORSMiddleware

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
from app.api.v1.documents import router as documents_router
from app.api.v1.finance import router as finance_router
from app.api.v1.runtime import router as runtime_router
from app.auth.router import router as auth_router
from app.chat_history.router import router as chat_history_router
from app.model_provider.router import router as model_provider_router
from app.providers.router import router as providers_router
from app.session.router import router as session_router
from app.skills.router import router as skills_router

app = FastAPI(
    title="ROXY JARVIS AI Gateway",
    description="Multi-provider AI abstraction layer with routing, failover, and attribution.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend to call the gateway
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routes under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(model_provider_router, prefix="/api/v1")
app.include_router(providers_router, prefix="/api/v1")
app.include_router(session_router, prefix="/api/v1")
app.include_router(chat_history_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(skills_router, prefix="/api/v1")
app.include_router(bank_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(runtime_router, prefix="/api/v1")
app.include_router(finance_router, prefix="/api/v1")


@app.on_event("startup")
async def on_startup():
    """Start the APScheduler job runner and ensure DB tables exist."""
    # Ensure all ORM models are registered before creating tables
    try:
        import app.auth.models  # noqa: F401
        import app.chat_history.models  # noqa: F401
        import app.models.bank_connection  # noqa: F401
        import app.models.budget  # noqa: F401
        import app.models.model  # noqa: F401
        import app.models.provider  # noqa: F401
        import app.models.spending_alert  # noqa: F401
        import app.models.token_usage  # noqa: F401
        import app.models.user_preference  # noqa: F401
        import app.session.models  # noqa: F401
        from app.db import Base, get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        import structlog
        structlog.get_logger().warning("db.init_tables_failed", error=str(exc))

    from app.job_scheduler import start_scheduler
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown():
    """Stop the APScheduler job runner when the backend stops."""
    from app.job_scheduler import stop_scheduler
    stop_scheduler()


# Email send alias route so both /api/v1/email/send and /api/v1/skills/email_send work
@app.post("/api/v1/email/send")
async def email_send_alias(
    req: dict,
    http_request: StarletteRequest = None,
):
    from app.skills.email_send import get_executor
    from app.skills.schemas import EmailSendRequest

    to = req.get("to", "")
    subject = req.get("subject", "")
    body = req.get("body", "")
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-gateway"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
