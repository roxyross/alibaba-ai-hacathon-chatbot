"""Runtime Router — Coordinator agent orchestration.

POST /api/v1/runtime/chat  — one-shot Coordinator routing with optional Critic pre-flight.
POST /api/v1/runtime/chat/stream  — streaming Coordinator with Critic pre-flight on final chunk.

The Coordinator classifies user intent, routes to the appropriate specialist agent,
and optionally runs a silent Critic pre-flight review on specialist responses.

Agent definitions live in .claude/agents/<slug>.md and are loaded at startup.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request as StarletteRequest, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole
from app.ai_gateway.services.router import AIRouter
from app.skills.critic_review import get_executor as critic_review_executor
from app.skills.schemas import CriticReviewRequest

log = structlog.get_logger()

router = APIRouter(prefix="/runtime", tags=["runtime"])

# Path to agent definition files (relative to repo root)
_AGENTS_DIR = Path(__file__).resolve().parents[4] / ".claude" / "agents"


# ---------------------------------------------------------------------------
# Intent classification — keyword-based router
# ---------------------------------------------------------------------------

# Finance keywords (money, bank, budget, spending, expenses, income, savings)
_FINANCE_PATTERNS = [
    re.compile(r"\b(bank|balance|account|transactions?|transfer)\b", re.I),
    re.compile(r"\b(budget|budgeting|spending|expenses?|expense)\b", re.I),
    re.compile(r"\b(income|salary|wages|earnings|savings)\b", re.I),
    re.compile(r"\b(credit.debit|card|loan|mortgage)\b", re.I),
    re.compile(r"\b(net.worth|financial|finances?|money)\b", re.I),
    re.compile(r"\b(bill|bills|pay|payment|due)\b", re.I),
]

# Critic keywords
_CRITIC_PATTERNS = [
    re.compile(r"\b(critique|critic|review|evaluate|assess|analyze)\b", re.I),
    re.compile(r"\b(opinion|second.opinion|feedback)\b", re.I),
    re.compile(r"\b(pros.cons|pros and cons|strengths?.*weaknesses?)\b", re.I),
]

# Automation keywords
_AUTOMATION_PATTERNS = [
    re.compile(r"\b(remind|reminder|schedule|recurring|daily|weekly|monthly)\b", re.I),
    re.compile(r"\b(every.morning|every.week|every.day|alarm|alert)\b", re.I),
    re.compile(r"\b(cron|定时|自动)\b", re.I),
]

# Research keywords
_RESEARCH_PATTERNS = [
    re.compile(r"\b(what.is|who.is|when.did|where.is|how.do)\b", re.I),
    re.compile(r"\b(search|look.up|find.information|research)\b", re.I),
    re.compile(r"\b(news|recent|latest|updated)\b", re.I),
]

# Coding keywords
_CODING_PATTERNS = [
    re.compile(r"\b(write.code|write.function|implement|debug|fix.bug)\b", re.I),
    re.compile(r"\b(code|python|javascript|typescript|java|rust|golang)\b", re.I),
    re.compile(r"\b(api|endpoint|function|class|module|import)\b", re.I),
    re.compile(r"\b(sql|query|database|table|schema)\b", re.I),
]

# Study keywords
_STUDY_PATTERNS = [
    re.compile(r"\b(flashcard|study|quiz|learn| memorize|revision)\b", re.I),
    re.compile(r"\b(chapter|course|lecture|textbook)\b", re.I),
]

# Browser keywords
_BROWSER_PATTERNS = [
    re.compile(r"\b(browse|navigate|go.to|open.website|visit)\b", re.I),
    re.compile(r"\b(fill.form|submit.form|login|download)\b", re.I),
]


def classify_intent(message: str) -> str:
    """Classify user message into an agent slug using keyword matching.

    Returns one of: finance | critic | automation | research | coding | study | browser | general
    """
    msg = message.strip()

    # Count matches per category
    scores: dict[str, int] = {
        "finance": sum(1 for p in _FINANCE_PATTERNS if p.search(msg)),
        "critic": sum(1 for p in _CRITIC_PATTERNS if p.search(msg)),
        "automation": sum(1 for p in _AUTOMATION_PATTERNS if p.search(msg)),
        "research": sum(1 for p in _RESEARCH_PATTERNS if p.search(msg)),
        "coding": sum(1 for p in _CODING_PATTERNS if p.search(msg)),
        "study": sum(1 for p in _STUDY_PATTERNS if p.search(msg)),
        "browser": sum(1 for p in _BROWSER_PATTERNS if p.search(msg)),
    }

    # Pick the highest-scoring non-zero category
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best
    return "general"


def load_agent_system_prompt(slug: str) -> str:
    """Load the system prompt from .claude/agents/<slug>.md.

    Strips YAML frontmatter and returns just the markdown body.
    Returns a default prompt if the agent file doesn't exist.
    """
    if not _AGENTS_DIR.exists():
        return f"You are the {slug} agent. Handle the user's request appropriately."

    agent_file = _AGENTS_DIR / f"{slug}.md"
    if not agent_file.exists():
        return f"You are the {slug} agent. Handle the user's request appropriately."

    content = agent_file.read_text(encoding="utf-8")
    # Strip YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].lstrip("\n")
    return content.strip()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RuntimeChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None)
    stream: bool = Field(default=False)
    # If set, bypasses intent classification and forces a specific agent
    agent_override: str | None = Field(default=None)


class RuntimeChatResponse(BaseModel):
    response: str
    agent_slug: str
    next_actions: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    critic_review: dict[str, Any] | None = Field(default=None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CACHED_PROMPTS: dict[str, str] = {}


def _get_agent_prompt(slug: str) -> str:
    if slug not in _CACHED_PROMPTS:
        _CACHED_PROMPTS[slug] = load_agent_system_prompt(slug)
    return _CACHED_PROMPTS[slug]


async def _call_ai_for_agent(
    agent_slug: str,
    user_message: str,
    stream: bool = False,
) -> tuple[str, str, str]:
    """Call the AI gateway with an agent-specific system prompt.

    Returns (response_text, provider, model).
    """
    system_prompt = _get_agent_prompt(agent_slug)

    router_ = AIRouter()
    request = AIRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=user_message),
        ],
        temperature=0.7,
        max_tokens=2048,
        stream=stream,
    )

    response: AIResponse = await router_.route(request)
    content = response.choices[0].message.content
    return content, response.provider, response.model


async def _run_critic_preflight(
    agent_response: str,
    agent_slug: str,
    user_message: str,
) -> dict[str, Any] | None:
    """Run silent critic pre-flight on a specialist response.

    Returns the critic review dict, or None if it fails.
    """
    try:
        executor = critic_review_executor()
        req = CriticReviewRequest(
            content=(
                f"[User query]\n{user_message}\n\n"
                f"[{agent_slug} agent response]\n{agent_response}"
            ),
            type="text",
            depth="quick",
            criteria=["logic", "clarity", "helpfulness"],
        )
        result = await executor.execute(req)
        return {
            "verdict": result.verdict,
            "overall": result.overall,
            "strengths": result.strengths,
            "weaknesses": [
                {"name": w.name, "why_it_matters": w.why_it_matters}
                for w in result.weaknesses
            ],
            "summary": result.summary,
        }
    except Exception as exc:
        log.warning("critic_preflight.failed", agent=agent_slug, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# POST /api/v1/runtime/chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=RuntimeChatResponse)
async def runtime_chat(
    body: RuntimeChatRequest,
    current_user: User = Depends(get_current_user),
) -> RuntimeChatResponse:
    """One-shot Coordinator chat — classify intent, route to agent, return response.

    Runs a silent Critic pre-flight review on the specialist response before
    returning it to the user (unless the response is very short, in which case
    the critic is skipped to avoid noise).
    """
    agent_slug = body.agent_override or classify_intent(body.message)

    log.info(
        "runtime.chat",
        user_id=str(current_user.id),
        message_preview=body.message[:80],
        agent=agent_slug,
        session_id=body.session_id,
    )

    try:
        response_text, _, _ = await _call_ai_for_agent(agent_slug, body.message)

        # Silent critic pre-flight — skip for very short responses (not enough to review meaningfully)
        critic_review: dict[str, Any] | None = None
        if len(response_text) > 200:
            critic_review = await _run_critic_preflight(
                response_text, agent_slug, body.message
            )
            log.info(
                "runtime.critic_preflight",
                agent=agent_slug,
                verdict=critic_review.get("verdict") if critic_review else None,
            )

        return RuntimeChatResponse(
            response=response_text,
            agent_slug=agent_slug,
            critic_review=critic_review,
        )

    except Exception as exc:
        log.error("runtime.chat.error", agent=agent_slug, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Runtime error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# POST /api/v1/runtime/chat/stream
# ---------------------------------------------------------------------------

@router.post("/chat/stream")
async def runtime_chat_stream(
    body: RuntimeChatRequest,
    current_user: User = Depends(get_current_user),
):
    """Streaming Coordinator chat — same as /chat but SSE with Critic pre-flight on final chunk."""
    agent_slug = body.agent_override or classify_intent(body.message)

    log.info(
        "runtime.chat.stream",
        user_id=str(current_user.id),
        message_preview=body.message[:80],
        agent=agent_slug,
    )

    async def event_generator():
        provider_name = "unknown"
        model_name = "unknown"
        full_response = []
        chunks_yielded = False

        try:
            system_prompt = _get_agent_prompt(agent_slug)
            router_ = AIRouter()
            request = AIRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=system_prompt),
                    Message(role=MessageRole.USER, content=body.message),
                ],
                temperature=0.7,
                max_tokens=2048,
                stream=True,
            )

            async for chunk in router_.route_stream(request):
                chunks_yielded = True
                if provider_name == "unknown":
                    provider_name = chunk.provider
                    model_name = chunk.model
                    yield f": provider={provider_name} model={model_name}\n\n".encode()

                delta = chunk.delta
                full_response.append(delta)

                data = json.dumps({
                    "delta": delta,
                    "provider": chunk.provider,
                    "model": chunk.model,
                    "done": chunk.done,
                    "agent_slug": agent_slug,
                })
                yield f"data: {data}\n\n".encode()

                if chunk.done:
                    break

            # Critic pre-flight on full response (only for non-trivial responses)
            if chunks_yielded and len("".join(full_response)) > 200:
                try:
                    critic_review = await _run_critic_preflight(
                        "".join(full_response), agent_slug, body.message
                    )
                    if critic_review:
                        review_data = json.dumps({
                            "type": "critic_review",
                            "review": critic_review,
                        })
                        yield f"data: {review_data}\n\n".encode()
                except Exception as exc:
                    log.warning("runtime.stream.critic_preflight.failed", error=str(exc))

            # Final attribution
            if chunks_yielded:
                final = json.dumps({
                    "done": True,
                    "provider": provider_name,
                    "model": model_name,
                    "agent_slug": agent_slug,
                })
                yield f"event: attribution\ndata: {final}\n\n".encode()

        except Exception as exc:
            import json as _json
            log.error("runtime.chat.stream.error", agent=agent_slug, error=str(exc))
            error_data = _json.dumps({
                "error": "runtime_error",
                "detail": str(exc),
                "done": True,
                "agent_slug": agent_slug,
            })
            yield f"data: {error_data}\n\n".encode()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
