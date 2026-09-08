"""FastAPI router that registers one endpoint per skill.

Architecture: FastAPI router per skill (one endpoint each).
Each skill module provides get_executor() which returns a SkillExecutor instance.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query, Request as StarletteRequest, status
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user
from app.auth.models import User

from app.skills.schemas import (
    BankConnectRequest,
    BankConnectResponse,
    BrowserFillFormRequest,
    BrowserFillFormResponse,
    BrowserNavigateRequest,
    BrowserNavigateResponse,
    CalendarReadRequest,
    CalendarReadResponse,
    CalculatorRequest,
    CalculatorResponse,
    CriticReviewRequest,
    CriticReviewResponse,
    DocumentRagQueryRequest,
    DocumentRagQueryResponse,
    DocumentIngestRequest,
    DocumentIngestResponse,
    EmailDraftRequest,
    EmailDraftResponse,
    EmailSendRequest,
    EmailSendResponse,
    FlashcardGenerateRequest,
    FlashcardGenerateResponse,
    QuizGenerateRequest,
    QuizGenerateResponse,
    RetrieveMemoryRequest,
    RetrieveMemoryResponse,
    ScheduleJobRequest,
    ScheduleJobResponse,
    SpeechToTextRequest,
    SpeechToTextResponse,
    StoreMemoryRequest,
    StoreMemoryResponse,
    TextToSpeechRequest,
    TextToSpeechResponse,
    WebSearchRequest,
    WebSearchResponse,
)

# Sensitive skills that require security-privacy confirmation gate
SENSITIVE_SKILLS = {"email_draft", "email_send", "browser_fill_form", "bank_connect"}

# Import get_executor factories directly from skill modules (not app.skills
# package) to avoid the circular import: app.skills.__init__ → router →
# app.skills calendar_read, which blocks before router.py finishes defining
# the `router` variable that __init__.py is trying to re-export.
from app.skills.store_memory import get_executor as store_memory_executor
from app.skills.retrieve_memory import get_executor as retrieve_memory_executor
from app.skills.calendar_read import get_executor as calendar_read_executor
from app.skills.calculator import get_executor as calculator_executor
from app.skills.email_draft import get_executor as email_draft_executor
from app.skills.web_search import get_executor as web_search_executor
from app.skills.browser_navigate import get_executor as browser_navigate_executor
from app.skills.browser_fill_form import get_executor as browser_fill_form_executor
from app.skills.bank_connect import get_executor as bank_connect_executor
from app.skills.critic_review import get_executor as critic_review_executor
from app.skills.schedule_job import (
    get_executor as schedule_job_executor,
    get_supported_timezones,
    get_timezone_regions,
    validate_timezone,
)
from app.skills.email_send import get_executor as email_send_executor
from app.skills.document_rag_query import get_executor as document_rag_query_executor
from app.skills.document_ingest import get_executor as document_ingest_executor
from app.skills.flashcard_generate import get_executor as flashcard_generate_executor
from app.skills.quiz_generate import get_executor as quiz_generate_executor
from app.skills.speech_to_text import get_executor as speech_to_text_executor
from app.skills.text_to_speech import get_executor as text_to_speech_executor


router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Sensitive skill confirmation gate
# ---------------------------------------------------------------------------

from typing import Any, TypeVar, cast

T = TypeVar("T")

# In-memory pending confirmations: user_id -> token -> (executor, input_data)
_pending_confirmations: dict[str, dict[str, tuple[Any, Any]]] = {}


async def _run_skill(
    executor: Any,
    input_data: Any,
    user: User,
    skill_slug: str = "",
    http_request: StarletteRequest | None = None,
) -> T:
    """Execute a skill and return its response, or raise HTTPException on failure.

    For sensitive skills (email_draft, browser_fill_form, bank_connect, schedule_job),
    the router returns HTTP 403 with a confirmation token instead of executing.
    The caller must then POST /skills/confirm with the token to proceed.
    """
    # Stamp authenticated user id into input_data for per-user data isolation.
    if hasattr(input_data, "model_fields") and "user_id" in input_data.model_fields:
        try:
            setattr(input_data, "user_id", str(user.id))
        except Exception:
            pass
    elif hasattr(input_data, "__dict__") and "user_id" in getattr(input_data, "__dict__", {}):
        try:
            setattr(input_data, "user_id", str(user.id))
        except Exception:
            pass

    # Read-only operations on schedule_job (like list or timezones) do not require confirmation
    op_str = str(getattr(input_data, "op", "")).lower()
    is_read_only = skill_slug == "schedule_job" and (op_str in ("list", "timezones") or getattr(input_data, "op", None) in ("list", "LIST"))
    # Security-privacy gate for sensitive skills (unless already explicitly confirmed or read-only)
    if skill_slug in SENSITIVE_SKILLS and not is_read_only and not getattr(input_data, "confirm", False):
        import secrets
        token = secrets.token_urlsafe(16)
        if user.id not in _pending_confirmations:
            _pending_confirmations[user.id] = {}
        _pending_confirmations[user.id][token] = (executor, input_data)

        action_desc = _describe_action(skill_slug, input_data)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "confirmation_required",
                "code": "CONFIRMATION_REQUIRED",
                "skill": skill_slug,
                "action": action_desc,
                "token": token,
                "message": (
                    f"This action requires your confirmation before proceeding. "
                    f"POST /api/v1/skills/confirm with the token to proceed, "
                    f"or GET /api/v1/skills/confirm/{token} to see details."
                ),
            },
        )

    try:
        res = await executor.execute(input_data)
        return cast(T, res)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill execution failed: {exc}",
        ) from exc


def _describe_action(skill_slug: str, input_data: Any) -> str:
    """Human-readable description of a sensitive action."""
    if skill_slug == "email_draft":
        return f"Send email to {getattr(input_data, 'to', '?')}"
    elif skill_slug == "browser_fill_form":
        return f"Fill and submit form on {getattr(input_data, 'url', '?')}"
    elif skill_slug == "bank_connect":
        op = getattr(input_data, 'op', '?')
        inst = getattr(input_data, 'institution', '')
        return f"Bank operation: {op} on {inst}" if inst else f"Bank operation: {op}"
    elif skill_slug == "schedule_job":
        name = getattr(input_data, 'name', '?')
        sched = getattr(input_data, 'schedule', '?')
        return f"Schedule job '{name}' to run at {sched}"
    return f"Execute {skill_slug}"


# ---------------------------------------------------------------------------
# GET /api/v1/skills/confirm/{token}  — preview a pending confirmation
# ---------------------------------------------------------------------------

class ConfirmPreview(BaseModel):
    skill: str
    action: str
    token: str
    valid: bool


@router.get("/confirm/{token}", response_model=ConfirmPreview)
async def skill_confirm_preview(
    token: str,
    current_user: User = Depends(get_current_user),
) -> ConfirmPreview:
    """Preview the action a confirmation token authorizes."""
    user_id = current_user.id
    if user_id not in _pending_confirmations or token not in _pending_confirmations[user_id]:
        raise HTTPException(status_code=404, detail="Token not found or expired")
    executor, input_data = _pending_confirmations[user_id][token]
    skill_slug = getattr(executor, "slug", "unknown")
    return ConfirmPreview(
        skill=skill_slug,
        action=_describe_action(skill_slug, input_data),
        token=token,
        valid=True,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/skills/confirm  — execute a confirmed skill
# ---------------------------------------------------------------------------

class ConfirmRequest(BaseModel):
    token: str


class ConfirmResponse(BaseModel):
    success: bool
    message: str


@router.post("/confirm", response_model=ConfirmResponse)
async def skill_confirm_execute(
    req: ConfirmRequest,
    current_user: User = Depends(get_current_user),
) -> ConfirmResponse:
    """Execute a skill after user confirmation via token."""
    user_id = current_user.id
    if user_id not in _pending_confirmations or req.token not in _pending_confirmations[user_id]:
        raise HTTPException(status_code=404, detail="Token not found or expired")

    executor, input_data = _pending_confirmations[user_id].pop(req.token)
    if not _pending_confirmations[user_id]:
        del _pending_confirmations[user_id]

    # Stamp confirmation — the skill's confirmation gate checks this flag
    try:
        input_data.confirm = True
    except AttributeError:
        pass  # Schema doesn't support confirm — skip

    try:
        result = await executor.execute(input_data)
        return ConfirmResponse(success=True, message="Action completed")
    except Exception as exc:
        return ConfirmResponse(success=False, message=f"Action failed: {exc}")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/store_memory
# ---------------------------------------------------------------------------

@router.post("/store_memory", response_model=StoreMemoryResponse)
async def skill_store_memory(
    req: StoreMemoryRequest,
    current_user: User = Depends(get_current_user),
) -> StoreMemoryResponse:
    """Persist an entry to the user's long-term memory store."""
    executor = store_memory_executor()
    return await _run_skill(executor, req, current_user, skill_slug="store_memory")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/retrieve_memory
# ---------------------------------------------------------------------------

@router.post("/retrieve_memory", response_model=RetrieveMemoryResponse)
async def skill_retrieve_memory(
    req: RetrieveMemoryRequest,
    current_user: User = Depends(get_current_user),
) -> RetrieveMemoryResponse:
    """Search the user's long-term memory store."""
    executor = retrieve_memory_executor()
    return await _run_skill(executor, req, current_user, skill_slug="retrieve_memory")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/calendar_read
# ---------------------------------------------------------------------------

@router.post("/calendar_read", response_model=CalendarReadResponse)
async def skill_calendar_read(
    req: CalendarReadRequest,
    current_user: User = Depends(get_current_user),
) -> CalendarReadResponse:
    """Parse and return events from an ICS calendar file or URL."""
    executor = calendar_read_executor()
    return await _run_skill(executor, req, current_user, skill_slug="calendar_read")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/calculator
# ---------------------------------------------------------------------------

@router.post("/calculator", response_model=CalculatorResponse)
async def skill_calculator(
    req: CalculatorRequest,
    current_user: User = Depends(get_current_user),
) -> CalculatorResponse:
    """Safely evaluate a mathematical expression and return the result."""
    executor = calculator_executor()
    return await _run_skill(executor, req, current_user, skill_slug="calculator")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/email_draft
# ---------------------------------------------------------------------------

@router.post("/email_draft", response_model=EmailDraftResponse)
async def skill_email_draft(
    req: EmailDraftRequest,
    current_user: User = Depends(get_current_user),
) -> EmailDraftResponse:
    """Compose a MIME email message (does not send). Returns the raw MIME string."""
    executor = email_draft_executor()
    return await _run_skill(executor, req, current_user, skill_slug="email_draft")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/email_send
# ---------------------------------------------------------------------------

@router.post("/email_send", response_model=EmailSendResponse)
async def skill_email_send(
    req: EmailSendRequest,
    current_user: User = Depends(get_current_user),
) -> EmailSendResponse:
    """Send a composed email via Gmail API or SMTP. Sensitive — requires confirmation."""
    executor = email_send_executor()
    return await _run_skill(executor, req, current_user, skill_slug="email_send")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/web_search
# ---------------------------------------------------------------------------

@router.post("/web_search", response_model=WebSearchResponse)
async def skill_web_search(
    req: WebSearchRequest,
    current_user: User = Depends(get_current_user),
) -> WebSearchResponse:
    """Perform a web search using DuckDuckGo (or Google/Bing). Returns ranked results."""
    executor = web_search_executor()
    return await _run_skill(executor, req, current_user, skill_slug="web_search")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/browser_navigate
# ---------------------------------------------------------------------------

@router.post("/browser_navigate", response_model=BrowserNavigateResponse)
async def skill_browser_navigate(
    req: BrowserNavigateRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserNavigateResponse:
    """Fetch a URL and return its title and a text preview of the content."""
    executor = browser_navigate_executor()
    return await _run_skill(executor, req, current_user, skill_slug="browser_navigate")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/browser_fill_form
# ---------------------------------------------------------------------------

@router.post("/browser_fill_form", response_model=BrowserFillFormResponse)
async def skill_browser_fill_form(
    req: BrowserFillFormRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserFillFormResponse:
    """Fetch a URL, fill form fields by selector, and optionally submit."""
    executor = browser_fill_form_executor()
    return await _run_skill(executor, req, current_user, skill_slug="browser_fill_form")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/bank_connect
# ---------------------------------------------------------------------------

@router.post("/bank_connect", response_model=BankConnectResponse)
async def skill_bank_connect(
    req: BankConnectRequest,
    current_user: User = Depends(get_current_user),
) -> BankConnectResponse:
    """Connect to a bank account via Plaid, list accounts, and retrieve transactions."""
    executor = bank_connect_executor()
    return await _run_skill(executor, req, current_user, skill_slug="bank_connect")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/critic_review
# ---------------------------------------------------------------------------

@router.post("/critic_review", response_model=CriticReviewResponse)
async def skill_critic_review(
    req: CriticReviewRequest,
    current_user: User = Depends(get_current_user),
) -> CriticReviewResponse:
    """Generate a structured critical review of text, code, plans, or decisions."""
    executor = critic_review_executor()
    return await _run_skill(executor, req, current_user, skill_slug="critic_review")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/schedule_job
# ---------------------------------------------------------------------------

@router.post("/schedule_job", response_model=ScheduleJobResponse)
async def skill_schedule_job(
    req: ScheduleJobRequest,
    current_user: User = Depends(get_current_user),
) -> ScheduleJobResponse:
    """Create, list, update, or cancel scheduled jobs (Automation Agent)."""
    executor = schedule_job_executor()
    return await _run_skill(executor, req, current_user, skill_slug="schedule_job")


# ---------------------------------------------------------------------------
# GET /api/v1/skills/schedule_job/timezones
# ---------------------------------------------------------------------------

@router.get("/schedule_job/timezones")
async def get_schedule_job_timezones(
    q: str | None = Query(default=None, description="Search term for city, country, or code"),
    region: str | None = Query(default=None, description="Filter by geographical region"),
) -> dict[str, Any]:
    """Return supported global timezones for scheduled jobs, with optional search and region filter."""
    timezones = get_supported_timezones(query=q, region=region)
    regions = get_timezone_regions()
    return {
        "success": True,
        "timezones": timezones,
        "total": len(timezones),
        "regions": regions,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/skills/schedule_job/timezones/regions
# ---------------------------------------------------------------------------

@router.get("/schedule_job/timezones/regions")
async def get_schedule_job_timezone_regions() -> dict[str, Any]:
    """Return all geographical timezone regions with counts."""
    regions = get_timezone_regions()
    return {"success": True, "regions": regions, "total": len(regions)}


# ---------------------------------------------------------------------------
# GET /api/v1/skills/schedule_job/timezones/search
# ---------------------------------------------------------------------------

@router.get("/schedule_job/timezones/search")
async def search_schedule_job_timezones(
    q: str = Query(..., min_length=1, description="Search query"),
) -> dict[str, Any]:
    """Search timezones by query (city, country, abbreviation, or UTC offset)."""
    matches = get_supported_timezones(query=q)
    return {"success": True, "query": q, "timezones": matches, "total": len(matches)}


# ---------------------------------------------------------------------------
# GET /api/v1/skills/schedule_job/timezones/validate
# ---------------------------------------------------------------------------

@router.get("/schedule_job/timezones/validate")
async def validate_schedule_job_timezone(
    tz: str = Query(..., min_length=1, description="Timezone name or alias to validate"),
) -> dict[str, Any]:
    """Validate a timezone string and return its canonical IANA identifier and metadata."""
    result = validate_timezone(tz)
    return {"success": True, **result}


# ---------------------------------------------------------------------------
# GET /api/v1/skills/timezones (Global aliases)
# ---------------------------------------------------------------------------

@router.get("/timezones")
async def get_timezones_alias(
    q: str | None = Query(default=None),
    region: str | None = Query(default=None),
) -> dict[str, Any]:
    """Alias route to retrieve supported world timezones."""
    return await get_schedule_job_timezones(q=q, region=region)


@router.get("/timezones/regions")
async def get_timezones_regions_alias() -> dict[str, Any]:
    """Alias route to retrieve timezone regions."""
    return await get_schedule_job_timezone_regions()


@router.get("/timezones/search")
async def search_timezones_alias(q: str = Query(..., min_length=1)) -> dict[str, Any]:
    """Alias route to search timezones."""
    return await search_schedule_job_timezones(q=q)


@router.get("/timezones/validate")
async def validate_timezone_alias(tz: str = Query(..., min_length=1)) -> dict[str, Any]:
    """Alias route to validate a timezone."""
    return await validate_schedule_job_timezone(tz=tz)


# ---------------------------------------------------------------------------
# POST /api/v1/skills/document_rag_query
# ---------------------------------------------------------------------------

@router.post("/document_rag_query", response_model=DocumentRagQueryResponse)
async def skill_document_rag_query(
    req: DocumentRagQueryRequest,
    current_user: User = Depends(get_current_user),
) -> DocumentRagQueryResponse:
    """RAG query over user-uploaded documents (Files Agent)."""
    executor = document_rag_query_executor()
    return await _run_skill(executor, req, current_user, skill_slug="document_rag_query")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/flashcard_generate
# ---------------------------------------------------------------------------

@router.post("/flashcard_generate", response_model=FlashcardGenerateResponse)
async def skill_flashcard_generate(
    req: FlashcardGenerateRequest,
    current_user: User = Depends(get_current_user),
) -> FlashcardGenerateResponse:
    """Generate flashcards from source material (Study Agent)."""
    executor = flashcard_generate_executor()
    return await _run_skill(executor, req, current_user, skill_slug="flashcard_generate")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/quiz_generate
# ---------------------------------------------------------------------------

@router.post("/quiz_generate", response_model=QuizGenerateResponse)
async def skill_quiz_generate(
    req: QuizGenerateRequest,
    current_user: User = Depends(get_current_user),
) -> QuizGenerateResponse:
    """Generate a self-test quiz from source material (Study Agent)."""
    executor = quiz_generate_executor()
    return await _run_skill(executor, req, current_user, skill_slug="quiz_generate")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/speech_to_text
# ---------------------------------------------------------------------------

@router.post("/speech_to_text", response_model=SpeechToTextResponse)
async def skill_speech_to_text(
    req: SpeechToTextRequest,
    current_user: User = Depends(get_current_user),
) -> SpeechToTextResponse:
    """Transcribe audio to text using OpenAI Whisper or Deepgram (Voice Agent)."""
    executor = speech_to_text_executor()
    return await _run_skill(executor, req, current_user, skill_slug="speech_to_text")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/text_to_speech
# ---------------------------------------------------------------------------

@router.post("/text_to_speech", response_model=TextToSpeechResponse)
async def skill_text_to_speech(
    req: TextToSpeechRequest,
    current_user: User = Depends(get_current_user),
) -> TextToSpeechResponse:
    """Synthesize speech from text using OpenAI TTS or ElevenLabs (Voice Agent)."""
    executor = text_to_speech_executor()
    return await _run_skill(executor, req, current_user, skill_slug="text_to_speech")


# ---------------------------------------------------------------------------
# POST /api/v1/skills/document_ingest
# ---------------------------------------------------------------------------

@router.post("/document_ingest", response_model=DocumentIngestResponse)
async def skill_document_ingest(
    req: DocumentIngestRequest,
    current_user: User = Depends(get_current_user),
) -> DocumentIngestResponse:
    """Parse a file and ingest it into the RAG vector store (Files Agent).

    Accepts base64-encoded file bytes and stores chunked text with embeddings.
    """
    executor = document_ingest_executor()
    return await _run_skill(executor, req, current_user, skill_slug="document_ingest")
