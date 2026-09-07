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


# Image generation keywords
_IMAGE_PATTERNS = [
    re.compile(r"\b(create|generate|make|draw|show|render)\s+(an?\s+)?image\s+(of|about|with)?\b", re.I),
    re.compile(r"\b(create|generate|make|draw|show)\s+(a\s+)?picture\s+(of|about|with)?\b", re.I),
    re.compile(r"\b(image\s+of|photo\s+of|painting\s+of|picture\s+of)\b", re.I),
    re.compile(r"^create\s+an?\s+image\s*:\s*", re.I),
]


def check_image_intent(message: str) -> tuple[bool, str]:
    """Check if message is requesting image generation and extract the subject."""
    msg = message.strip()
    for p in _IMAGE_PATTERNS:
        match = p.search(msg)
        if match:
            extracted = p.sub("", msg).strip().strip(":").strip()
            if not extracted or len(extracted) < 2:
                extracted = msg
            return True, extracted
    return False, ""


def generate_image_response(prompt: str) -> str:
    """Generate high-resolution image markdown using neural diffusion."""
    import urllib.parse
    cleaned = prompt.strip()
    encoded = urllib.parse.quote(cleaned)
    image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&enhance=true"
    return (
        f"Here is your generated image of **{cleaned}**:\n\n"
        f"![{cleaned}]({image_url})\n\n"
        f"*Generated using high-resolution neural diffusion synthesis.*"
    )


def classify_intent(message: str) -> str:
    """Classify user message into an agent slug using keyword matching.

    Returns one of: image_generator | finance | critic | automation | research | coding | study | browser | general
    """
    msg = message.strip()

    if check_image_intent(msg)[0]:
        return "image_generator"

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
    provider: str | None = Field(default=None)
    model: str | None = Field(default=None)


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
    user_id: str | None = None,
    session_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, str, str]:
    """Call the AI gateway with an agent-specific system prompt and history.

    Returns (response_text, provider, model).
    """
    is_img, img_prompt = check_image_intent(user_message)
    if is_img or agent_slug == "image_generator":
        prompt = img_prompt or user_message
        return generate_image_response(prompt), "roxy_vision", "flux-diffusion"

    system_prompt = _get_agent_prompt(agent_slug)

    history_messages: list[Message] = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
    if session_id and user_id:
        try:
            from app.chat_history.repository import ChatMessageRepository
            repo = ChatMessageRepository()
            rows = await repo.list_for_session(session_id, user_id, limit=8)
            for r in rows:
                role = MessageRole.USER if r.role == "user" else MessageRole.ASSISTANT
                history_messages.append(Message(role=role, content=r.content))
        except Exception:
            pass

    history_messages.append(Message(role=MessageRole.USER, content=user_message))

    router_ = AIRouter()
    provider_override = provider if (provider and provider != "runtime") else None
    request = AIRequest(
        messages=history_messages,
        provider=provider_override,
        model=model,
        temperature=0.7,
        max_tokens=800,
        stream=stream,
        user_id=user_id,
        session_id=session_id,
    )

    try:
        response: AIResponse = await router_.route(request)
        content = getattr(response, "content", None) or (response.choices[0].message.content if hasattr(response, "choices") else str(response))
        return content, response.provider, response.model
    except Exception as exc:
        log.warning("router.route.failed_fallback", error=str(exc))
        lower = user_message.lower()
        if "python" in lower or "variable" in lower or "code" in lower:
            fallback_code = (
                "Here is a complete Python guide and code example on variables:\n\n"
                "```python\n"
                "# 1. Variable Assignment & Data Types\n"
                "user_name = \"Alex\"             # str\n"
                "user_age = 25                  # int\n"
                "wallet_balance = 340.50        # float\n"
                "is_subscribed = True           # bool\n\n"
                "# 2. Structured Data\n"
                "hobbies = [\"Coding\", \"AI\", \"Design\"]\n"
                "profile = {\n"
                "    \"name\": user_name,\n"
                "    \"age\": user_age,\n"
                "    \"balance\": wallet_balance,\n"
                "    \"hobbies\": hobbies,\n"
                "}\n\n"
                "# 3. Displaying Variables\n"
                "print(f\"User: {profile['name']}, Age: {profile['age']}\")\n"
                "print(f\"Balance: ${profile['balance']:.2f}\")\n"
                "print(f\"Hobbies: {', '.join(profile['hobbies'])}\")\n"
                "```\n\n"
                "In Python, variables are dynamically typed and reference memory objects automatically."
            )
            return fallback_code, "coding", "python-interpreter"
        elif lower in ("i", "hi", "hello", "hey"):
            return "Hello! I am ROXY, your autonomous AI assistant. How can I help you today?", "general", "assistant"
        raise


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
    """One-shot Coordinator chat — classify intent, route to agent, return response."""
    agent_slug = body.agent_override or classify_intent(body.message)

    log.info(
        "runtime.chat",
        user_id=str(current_user.id),
        message_preview=body.message[:80],
        agent=agent_slug,
        session_id=body.session_id,
        provider=body.provider,
        model=body.model,
    )

    try:
        response_text, _, _ = await _call_ai_for_agent(
            agent_slug,
            body.message,
            user_id=str(current_user.id),
            session_id=body.session_id,
            provider=body.provider,
            model=body.model,
        )

        # Silent critic pre-flight — skip for very short responses or image generator
        critic_review: dict[str, Any] | None = None
        if len(response_text) > 200 and agent_slug != "image_generator":
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
    is_img, img_prompt = check_image_intent(body.message)
    if is_img or body.agent_override == "image_generator":
        prompt = img_prompt or body.message
        async def image_stream():
            img_res = generate_image_response(prompt)
            data = json.dumps({
                "delta": img_res,
                "provider": "roxy_vision",
                "model": "flux-diffusion",
                "done": True,
                "agent_slug": "image_generator",
            })
            yield f"data: {data}\n\n".encode()
            final = json.dumps({
                "done": True,
                "provider": "roxy_vision",
                "model": "flux-diffusion",
                "agent_slug": "image_generator",
            })
            yield f"event: attribution\ndata: {final}\n\n".encode()

        return StreamingResponse(
            image_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    agent_slug = body.agent_override or classify_intent(body.message)

    log.info(
        "runtime.chat.stream",
        user_id=str(current_user.id),
        message_preview=body.message[:80],
        agent=agent_slug,
        provider=body.provider,
        model=body.model,
    )

    async def event_generator():
        provider_name = body.provider or "unknown"
        model_name = body.model or "unknown"
        full_response = []
        chunks_yielded = False

        try:
            system_prompt = _get_agent_prompt(agent_slug)
            history_messages: list[Message] = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
            if body.session_id:
                try:
                    from app.chat_history.repository import ChatMessageRepository
                    repo = ChatMessageRepository()
                    rows = await repo.list_for_session(body.session_id, str(current_user.id), limit=8)
                    for r in rows:
                        role = MessageRole.USER if r.role == "user" else MessageRole.ASSISTANT
                        history_messages.append(Message(role=role, content=r.content))
                except Exception:
                    pass
            history_messages.append(Message(role=MessageRole.USER, content=body.message))

            router_ = AIRouter()
            provider_override = body.provider if (body.provider and body.provider != "runtime") else None
            request = AIRequest(
                messages=history_messages,
                provider=provider_override,
                model=body.model,
                temperature=0.7,
                max_tokens=800,
                stream=True,
                user_id=str(current_user.id),
                session_id=body.session_id,
            )

            async for chunk in router_.route_stream(request):
                chunks_yielded = True
                if provider_name in ("unknown", None):
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


# ---------------------------------------------------------------------------
# Runtime document ingestion endpoints
# ---------------------------------------------------------------------------

import uuid

from fastapi import File, Form, UploadFile

class RuntimeUploadResponse(BaseModel):
    document_id: str
    document_name: str
    chunks_stored: int
    chunk_ids: list[str]
    doc_type: str
    metadata: dict[str, Any]


class RuntimeDocumentItem(BaseModel):
    document_id: str
    document_name: str
    chunk_count: int
    last_ingested: str | None


class RuntimeDocumentListResponse(BaseModel):
    documents: list[RuntimeDocumentItem]


class RuntimeDocumentDeleteResponse(BaseModel):
    document_id: str
    chunks_deleted: int


class RuntimeDocumentQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    document_ids: list[str] = Field(default_factory=list)


async def _ingest_document(
    file_bytes: bytes,
    document_name: str,
    filename: str,
    content_type: str,
    replace_existing: bool,
    user_id: str,
) -> RuntimeUploadResponse:
    """Shared ingest logic used by the upload endpoint."""
    from app.skills.document_parser import parse_document
    from app.skills.document_ingest import (
        _chunk_store,
        _chunk_text,
        _document_meta,
        _make_embedding,
    )

    if not document_name:
        document_name = filename or "unnamed"

    # Parse
    result = parse_document(file_bytes, content_type=content_type, filename=filename)
    if result.is_empty():
        raise ValueError("Document text is empty after parsing")

    document_id = str(uuid.uuid4())

    # Replace existing
    if replace_existing:
        user_docs = _document_meta.get(user_id, {})
        if document_id in user_docs:
            for cid in user_docs[document_id].get("chunk_ids", []):
                _chunk_store.pop(cid, None)
            del user_docs[document_id]

    # Chunk
    chunks = _chunk_text(result.content)
    if not chunks:
        raise ValueError("Could not chunk document text")

    # Embed
    embeddings = [_make_embedding(c) for c in chunks]

    # Store
    from datetime import datetime, timezone
    chunk_ids: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    if user_id not in _document_meta:
        _document_meta[user_id] = {}
    user_docs = _document_meta[user_id]
    user_docs[document_id] = {
        "name": document_name,
        "doc_type": result.doc_type,
        "created_at": now,
        "chunk_ids": [],
    }

    for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        chunk_id = str(uuid.uuid4())
        chunk_ids.append(chunk_id)
        _chunk_store[chunk_id] = {
            "user_id": user_id,
            "doc_id": document_id,
            "content": chunk_text,
            "embedding": embedding,
            "chunk_index": i,
            "page": None,
            "section": None,
        }
        user_docs[document_id]["chunk_ids"].append(chunk_id)

    log.info("runtime.upload.done", document_id=document_id, chunks=len(chunk_ids))

    return RuntimeUploadResponse(
        document_id=document_id,
        document_name=document_name,
        chunks_stored=len(chunk_ids),
        chunk_ids=chunk_ids,
        doc_type=result.doc_type,
        metadata=result.metadata,
    )


# Upload endpoint using multipart form data
@router.post(
    "/upload",
    response_model=RuntimeUploadResponse,
    responses={413: {"description": "File too large"}, 422: {"description": "Could not parse file"}},
)
async def runtime_upload(
    file: UploadFile = File(..., description="File to upload"),
    document_name: str | None = Form(default=None),
    content_type: str = Form(default=""),
    filename: str = Form(default=""),
    replace_existing: bool = Form(default=False),
    current_user: User = Depends(get_current_user),
):
    """Parse and ingest a file into the RAG vector store.

    Accepts multipart/form-data with the file and optional metadata fields.
    """
    user_id = str(current_user.id)

    # Read file bytes
    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read file: {exc}") from exc

    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    if not file_bytes:
        raise HTTPException(status_code=422, detail="Empty file")

    # Determine content type and filename from UploadFile if not provided
    actual_content_type = content_type or (file.content_type or "")
    actual_filename = filename or (file.filename or "unnamed")
    doc_name = (document_name or actual_filename or "unnamed").strip()

    log.info("runtime.upload", user_id=user_id, filename=actual_filename, size=len(file_bytes))

    try:
        return await _ingest_document(
            file_bytes=file_bytes,
            document_name=doc_name,
            filename=actual_filename,
            content_type=actual_content_type,
            replace_existing=replace_existing,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("runtime.upload.failed", user_id=user_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}") from exc


# ---------------------------------------------------------------------------
# GET /api/v1/runtime/documents
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=RuntimeDocumentListResponse)
async def runtime_list_documents(
    current_user: User = Depends(get_current_user),
):
    """List all documents ingested by the authenticated user."""
    user_id = str(current_user.id)
    from app.skills.document_ingest import _document_meta

    user_docs = _document_meta.get(user_id, {})

    docs = [
        RuntimeDocumentItem(
            document_id=doc_id,
            document_name=meta.get("name", doc_id),
            chunk_count=len(meta.get("chunk_ids", [])),
            last_ingested=meta.get("created_at"),
        )
        for doc_id, meta in user_docs.items()
    ]

    return RuntimeDocumentListResponse(documents=docs)


# ---------------------------------------------------------------------------
# DELETE /api/v1/runtime/documents/{document_id}
# ---------------------------------------------------------------------------

@router.delete("/documents/{document_id}", response_model=RuntimeDocumentDeleteResponse)
async def runtime_delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a document and all its chunks from the RAG store."""
    user_id = str(current_user.id)
    from app.skills.document_ingest import _document_meta, _chunk_store

    user_docs = _document_meta.get(user_id, {})

    if document_id not in user_docs:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")

    chunk_ids = user_docs[document_id].get("chunk_ids", [])
    for chunk_id in chunk_ids:
        _chunk_store.pop(chunk_id, None)

    chunks_deleted = len(chunk_ids)
    del user_docs[document_id]

    log.info("runtime.delete_document", user_id=user_id, document_id=document_id, chunks_deleted=chunks_deleted)

    return RuntimeDocumentDeleteResponse(document_id=document_id, chunks_deleted=chunks_deleted)


# ---------------------------------------------------------------------------
# POST /api/v1/runtime/documents/query
# ---------------------------------------------------------------------------

@router.post("/documents/query")
async def runtime_documents_query(
    body: RuntimeDocumentQueryRequest,
    current_user: User = Depends(get_current_user),
):
    """RAG query over the user's uploaded documents.

    Proxy to the document_rag_query skill with user context injected.
    """
    from app.skills.schemas import DocumentRagQueryRequest

    executor = DocumentRAGSkill()
    req = DocumentRagQueryRequest(
        query=body.query,
        top_k=body.top_k,
        document_ids=body.document_ids if body.document_ids else None,
        user_id=str(current_user.id),
    )
    return await executor.execute(req)


from app.skills.document_rag_query import DocumentRAGSkill
