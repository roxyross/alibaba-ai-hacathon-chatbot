"""ROXY JARVIS runtime — FastAPI app factory.

Binds to :8001 by default. Loads agent and skill registries at
startup, registers skill implementations (the PR 2 stub for
`web_search`; more in PR 3), and exposes:

  POST /api/v1/runtime/chat     — the main user-facing endpoint
  POST /api/v1/runtime/upload   — ingest a document (PDF/DOCX/PPTX/MD/TXT)
  GET  /api/v1/runtime/agents   — list all loaded agents
  GET  /api/v1/runtime/skills   — list all loaded skills
  GET  /health/live             — process is up
  GET  /health/ready            — registries populated, gateway reachable
  GET  /docs                    — OpenAPI UI

Run with: `uv run python -m runtime.main` from the `runtime/` directory.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from runtime.agents.executor import AgentExecutor
from runtime.agents.registry import AgentRegistry, build_registry as build_agent_registry
from runtime.agents.security_gate import SecurityGate
from runtime.api.chat import router as chat_router
from runtime.api.health import router as health_router
from runtime.api.voice import router as voice_router
from runtime.api.browser import router as browser_router
from runtime.api.upload import router as upload_router
from runtime.api.documents import router as documents_router
from runtime.config import settings
from runtime.coordinator.classifier import Classifier
from runtime.coordinator.router import Coordinator
from runtime.infrastructure.gateway_client import GatewayClient
from runtime.infrastructure.logging import configure_logging
from runtime.skills.executor import SkillExecutor
from runtime.skills.registry import SkillRegistry, build_registry as build_skill_registry
from runtime.skills import skill_schemas as schemas
from runtime.skills.web_search import web_search
from runtime.skills.code_generate import code_generate
from runtime.skills.code_explain import code_explain
from runtime.skills.code_debug import code_debug
from runtime.skills.task_breakdown import task_breakdown
from runtime.skills.schedule_job import schedule_job, set_coordinator as _set_scheduler_coord
from runtime.skills.document_ingest import document_ingest
from runtime.skills.document_rag_query import document_rag_query
from runtime.skills.flashcard_generate import flashcard_generate
from runtime.skills.quiz_generate import quiz_generate
from runtime.skills.speech_to_text import speech_to_text
from runtime.skills.text_to_speech import text_to_speech
from runtime.skills.browser_navigate import browser_navigate
from runtime.skills.browser_fill_form import browser_fill_form
from runtime.skills.store_memory import store_memory
from runtime.skills.retrieve_memory import retrieve_memory
from runtime.skills.calculator import calculator
from runtime.skills.calendar_read import calendar_read
from runtime.skills.email_draft import email_draft
from runtime.skills.email_send import email_send
from runtime.skills.bank_connect import bank_connect
from runtime.skills.critic_review import critic_review

log = structlog.get_logger()


def create_app() -> FastAPI:
    """Build the FastAPI app. Idempotent; safe to call from tests."""
    configure_logging(level=settings.log_level, as_json=settings.log_json)

    app = FastAPI(
        title="ROXY JARVIS Runtime",
        description=(
            "Multi-agent runtime: loads .claude/agents/*.md and "
            ".claude/skills/*/SKILL.md, classifies user queries, and "
            "dispatches them to specialist agents."
        ),
        version="0.1.0",
        docs_url="/docs",
    )

    # CORS — same convention as the backend (open in dev, restricted in prod).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Registries ------------------------------------------------------
    agent_registry: AgentRegistry = build_agent_registry()
    skill_registry: SkillRegistry = build_skill_registry()

    # ---- Skill implementations ------------------------------------------
    skill_executor = SkillExecutor()
    # Core skills
    skill_executor.register("web_search", web_search, schemas.WebSearchInput)
    skill_executor.register("code_generate", code_generate, schemas.CodeGenerateInput)
    skill_executor.register("code_explain", code_explain, schemas.CodeExplainInput)
    skill_executor.register("code_debug", code_debug, schemas.CodeDebugInput)
    skill_executor.register("task_breakdown", task_breakdown, schemas.TaskBreakdownInput)
    skill_executor.register("schedule_job", schedule_job, schemas.ScheduleJobInput)
    # Files / RAG
    skill_executor.register("document_ingest", document_ingest, schemas.DocumentIngestInput)
    skill_executor.register("document_rag_query", document_rag_query, schemas.DocumentRagQueryInput)
    # Study
    skill_executor.register("flashcard_generate", flashcard_generate, schemas.FlashcardGenerateInput)
    skill_executor.register("quiz_generate", quiz_generate, schemas.QuizGenerateInput)
    # Voice
    skill_executor.register("speech_to_text", speech_to_text, schemas.SpeechToTextInput)
    skill_executor.register("text_to_speech", text_to_speech, schemas.TextToSpeechInput)
    # Browser
    skill_executor.register("browser_navigate", browser_navigate, schemas.BrowserNavigateInput)
    skill_executor.register("browser_fill_form", browser_fill_form, schemas.BrowserFillFormInput)
    # Memory
    skill_executor.register("store_memory", store_memory, schemas.StoreMemoryInput)
    skill_executor.register("retrieve_memory", retrieve_memory, schemas.RetrieveMemoryInput)
    # Utility
    skill_executor.register("calculator", calculator, schemas.CalculatorInput)
    skill_executor.register("calendar_read", calendar_read, schemas.CalendarReadInput)
    skill_executor.register("email_draft", email_draft, schemas.EmailDraftInput)
    skill_executor.register("email_send", email_send, schemas.EmailSendInput)
    # Finance
    skill_executor.register("bank_connect", bank_connect, schemas.BankConnectInput)
    # Evaluation
    skill_executor.register("critic_review", critic_review, schemas.CriticReviewInput)
    if not skill_executor.is_registered("web_search"):
        # Defensive: this should be impossible.
        log.error("skill.web_search.register_failed")

    # ---- Infrastructure --------------------------------------------------
    gateway_client = GatewayClient()

    # ---- Coordinator ----------------------------------------------------
    classifier = Classifier(agent_registry)
    agent_executor = AgentExecutor(gateway_client)
    agent_executor.set_skill_executor(skill_executor)
    # Security gate — invokes the security-privacy agent before sensitive skills
    security_gate = SecurityGate(agent_registry, agent_executor)
    agent_executor.set_security_gate(security_gate)
    coordinator = Coordinator(agent_registry, classifier, agent_executor, security_gate)
    # Give the scheduler a reference to the coordinator so scheduled jobs can fire
    _set_scheduler_coord(coordinator)

    # ---- Stash on app state ---------------------------------------------
    app.state.agent_registry = agent_registry
    app.state.skill_registry = skill_registry
    app.state.skill_executor = skill_executor
    app.state.gateway_client = gateway_client
    app.state.coordinator = coordinator

    log.info(
        "runtime.startup",
        agents=len(agent_registry),
        routable=len(agent_registry.routable()),
        skills=len(skill_registry),
        backend=settings.backend_base_url,
    )

    # ---- Routes ---------------------------------------------------------
    app.include_router(chat_router)
    app.include_router(health_router)
    app.include_router(voice_router)
    app.include_router(browser_router)
    app.include_router(upload_router)
    app.include_router(documents_router)

    @app.get("/api/v1/runtime/agents")
    async def list_agents() -> dict:
        return {
            "agents": [
                {
                    "slug": a.slug,
                    "description": a.description,
                    "routable": a.routable,
                    "sensitive": a.sensitive,
                    "internal": a.internal,
                }
                for a in agent_registry.all()
            ]
        }

    @app.get("/api/v1/runtime/skills")
    async def list_skills() -> dict:
        return {
            "skills": [
                {
                    "slug": s.slug,
                    "description": s.description,
                    "sensitive": s.sensitive,
                    "internal": s.internal,
                    "registered": skill_executor.is_registered(s.slug),
                }
                for s in skill_registry.all()
            ]
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "runtime.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
