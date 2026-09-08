"""Pydantic schemas for all skill request/response models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

class Importance(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    FOREVER = "forever"


class MemorySource(str, Enum):
    USER_EXPLICIT = "user:explicit"
    AGENT_FILES = "agent:files-agent"
    AGENT_STUDY = "agent:study-agent"
    AGENT_AUTOMATION = "agent:automation"
    JOB_NIGHTLY_CURATOR = "job:nightly-curator"
    JOB_SCHEDULED = "job:scheduled"


# ---------------------------------------------------------------------------
# store_memory
# ---------------------------------------------------------------------------

class StoreMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list)
    importance: Importance = Importance.NORMAL
    source: MemorySource | None = None
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")

    @field_validator("tags")
    @classmethod
    def tags_not_empty(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if t.strip()]


class StoreMemoryResponse(BaseModel):
    entry_id: str
    stored_at: datetime
    duplicate: bool = False
    existing_entry_id: str | None = None


# ---------------------------------------------------------------------------
# retrieve_memory
# ---------------------------------------------------------------------------

class RetrieveMemoryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: Annotated[int, Field(ge=1, le=50)] = 5
    tags: list[str] = Field(default_factory=list)
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class MemoryEntry(BaseModel):
    entry_id: str
    content: str
    tags: list[str]
    importance: Importance
    source: MemorySource | None
    stored_at: datetime
    relevance_score: float


class RetrieveMemoryResponse(BaseModel):
    entries: list[MemoryEntry]
    query: str


# ---------------------------------------------------------------------------
# calendar_read
# ---------------------------------------------------------------------------

class CalendarReadRequest(BaseModel):
    start_date: str = Field(..., description="ISO 8601 date, e.g. 2026-09-06")
    end_date: str = Field(..., description="ISO 8601 date, inclusive")
    calendar_path: str | None = Field(
        default=None,
        description="Path to .ics file or ICS URL. Defaults to configured default calendar.",
    )
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class CalendarEvent(BaseModel):
    uid: str
    summary: str
    start: datetime
    end: datetime | None
    description: str | None
    location: str | None
    all_day: bool = False


class CalendarReadResponse(BaseModel):
    events: list[CalendarEvent]
    calendar_path: str | None


# ---------------------------------------------------------------------------
# calculator
# ---------------------------------------------------------------------------

class CalculatorRequest(BaseModel):
    expression: str = Field(..., min_length=1, max_length=500)


class CalculatorResponse(BaseModel):
    expression: str
    result: float | None
    error: str | None


# ---------------------------------------------------------------------------
# email_send
# ---------------------------------------------------------------------------

class EmailSendRequest(BaseModel):
    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    confirm: bool = Field(
        default=False,
        description="Must be True to dispatch. Runtime must have obtained user confirmation first.",
    )
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")
    # Optional direct SMTP credentials for real email dispatch
    smtp_host: str | None = Field(default=None, description="SMTP server host (e.g. smtp.gmail.com)")
    smtp_port: int | None = Field(default=None, description="SMTP server port (e.g. 587 or 465)")
    smtp_user: str | None = Field(default=None, description="SMTP username / email address")
    smtp_pass: str | None = Field(default=None, description="SMTP password / Gmail App Password")
    smtp_from: str | None = Field(default=None, description="From email address")

    @field_validator("to", "cc", "bcc")
    @classmethod
    def validate_emails(cls, v: str | list[str]) -> str | list[str]:
        return v


class EmailSendResponse(BaseModel):
    success: bool
    delivery_status: str = Field(..., description="One of: not_sent, queued, sent, failed")
    message_id: str | None = None
    sent_at: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# email_draft
# ---------------------------------------------------------------------------

class EmailDraftRequest(BaseModel):
    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def validate_emails(cls, v: str | list[str]) -> str | list[str]:
        if isinstance(v, list):
            return v
        return v


class EmailDraftResponse(BaseModel):
    to: str
    cc: list[str]
    bcc: list[str]
    subject: str
    body: str
    raw_mime: str


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

class WebSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    num_results: Annotated[int, Field(ge=1, le=20)] = 10
    source: str | None = Field(default=None, description="Specific search engine: 'google', 'bing', 'duckduckgo'")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source: str


class WebSearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total_results: int | None = None


# ---------------------------------------------------------------------------
# browser_navigate
# ---------------------------------------------------------------------------

class BrowserNavigateRequest(BaseModel):
    url: str = Field(..., description="URL to navigate to")
    wait_for: str | None = Field(
        default=None,
        description="CSS selector or text content to wait for before returning",
    )
    timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 30
    js_enabled: bool = Field(
        default=False,
        description="Use Playwright for JS-heavy sites (required for SPAs, bank sites, etc.). Falls back to httpx if Playwright is not installed.",
    )


class BrowserNavigateResponse(BaseModel):
    url: str
    title: str | None
    final_url: str
    content_preview: str = Field(..., max_length=2000)
    success: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# browser_fill_form
# ---------------------------------------------------------------------------

class FormField(BaseModel):
    selector: str = Field(..., description="CSS selector for the form field")
    value: str


class BrowserFillFormRequest(BaseModel):
    url: str = Field(..., description="URL of the page with the form")
    fields: list[FormField] = Field(..., min_length=1)
    submit: bool = Field(default=False, description="Whether to submit the form after filling")
    wait_for: str | None = None


class BrowserFillFormResponse(BaseModel):
    url: str
    filled_fields: list[str]
    submitted: bool
    success: bool
    error: str | None = None
    content_preview: str | None = None


# ---------------------------------------------------------------------------
# bank_connect
# ---------------------------------------------------------------------------


class BankConnectRequest(BaseModel):
    op: str = Field(
        ...,
        description="Operation: 'connect', 'disconnect', 'list_accounts', 'get_transactions', 'get_balance'",
    )
    institution: str | None = Field(default=None, description="Bank name (e.g. 'Chase', 'Bank of America')")
    access_token: str | None = Field(default=None, description="Plaid access token from OAuth callback")
    account_ids: list[str] | None = Field(default=None, description="Account IDs to query (defaults to all)")
    start_date: str | None = Field(default=None, description="Start date for transactions (YYYY-MM-DD)")
    end_date: str | None = Field(default=None, description="End date for transactions (YYYY-MM-DD)")
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class BankAccount(BaseModel):
    connection_id: str
    institution: str | None
    account_id: str
    name: str
    type: str
    mask: str | None
    balance: float | None


class BankTransaction(BaseModel):
    account_id: str
    date: str
    description: str
    amount: float
    category: str
    pending: bool


class BankConnectResponse(BaseModel):
    op: str
    success: bool
    message: str | None = None
    link_token: str | None = None
    institution: str | None = None
    accounts: list[BankAccount] | None = None
    transactions: list[BankTransaction] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# critic_review
# ---------------------------------------------------------------------------


class CriticReviewRequest(BaseModel):
    content: str = Field(..., min_length=1, description="The text, code, plan, or decision to review")
    type: str = Field(
        default="text",
        description="Content type: 'text', 'code', 'plan', 'decision', 'research'",
    )
    depth: str = Field(
        default="standard",
        description="Review depth: 'quick', 'standard', 'deep'",
    )
    criteria: list[str] | None = Field(
        default=None,
        description="Evaluation criteria to focus on (defaults to logic/evidence/clarity/completeness)",
    )
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class CriticWeakness(BaseModel):
    name: str
    evidence: str
    why_it_matters: str
    suggested_fix: str | None


class CriticReviewResponse(BaseModel):
    verdict: str = Field(..., description="Overall verdict: 'strong', 'adequate', 'weak', 'flawed'")
    overall: str = Field(..., description="One-sentence assessment")
    strengths: list[str]
    weaknesses: list[CriticWeakness]
    minor_issues: list[str]
    missing_perspectives: list[str]
    summary: str
    depth: str
    criteria_evaluated: list[str]


# ---------------------------------------------------------------------------
# schedule_job  (used by Automation Agent)
# ---------------------------------------------------------------------------

class ScheduleJobOp(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    LIST = "list"
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    TIMEZONES = "timezones"


class JobAction(BaseModel):
    agent_slug: str = Field(..., description="Agent to invoke, e.g. 'research', 'files', 'browser'")
    skill_slug: str | None = Field(default=None, description="Skill to invoke (optional)")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Inputs to the agent/skill")


class ScheduleJobRequest(BaseModel):
    op: ScheduleJobOp = Field(..., description="Operation: create, update, list, cancel, pause, resume, timezones")
    job_id: str | None = Field(default=None, description="Required for cancel/pause/resume/update ops")
    name: str | None = Field(default=None, description="Job name (required for create/update)")
    schedule: str | None = Field(default=None, description="Cron expression or ISO-8601 timestamp")
    timezone: str | None = Field(default=None, description="IANA timezone, e.g. 'America/New_York'")
    action: JobAction | None = Field(default=None, description="Action to run when job fires")
    confirm_on_fire: bool = Field(default=False, description="Re-confirm before sensitive actions at fire time")
    tag: str | None = Field(default=None, description="Filter by tag (list op only)")
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")
    confirm: bool = Field(default=True, description="Confirmation flag for skill execution.")


class JobEntry(BaseModel):
    job_id: str
    name: str
    schedule: str
    timezone: str
    action: JobAction
    confirm_on_fire: bool
    status: str  # "active", "paused", "fired"
    created_at: datetime
    next_fire_at: datetime | None
    tag: str | None


class ScheduleJobResponse(BaseModel):
    op: str
    success: bool
    job_id: str | None = None
    jobs: list[JobEntry] | None = None
    timezones: list[dict[str, Any]] | None = None
    message: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# document_rag_query  (used by Files Agent)
# ---------------------------------------------------------------------------

class DocumentRagQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="User's question")
    top_k: Annotated[int, Field(ge=1, le=50)] = 8
    document_ids: list[str] | None = Field(default=None, description="Scope to specific uploaded docs")
    rerank: bool = Field(default=False, description="Re-rank results with a cross-encoder")
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class DocumentIngestRequest(BaseModel):
    document_id: str | None = Field(default=None, description="Stable ID; a new UUID is generated if None")
    document_name: str = Field(..., min_length=1, max_length=500, description="Human-readable name shown in citations")
    file_bytes: str = Field(..., description="Base64-encoded file content")
    content_type: str = Field(default="", description="MIME type of the file")
    filename: str = Field(default="", description="Original filename for extension-based dispatch")
    replace_existing: bool = Field(default=False, description="Delete existing chunks before ingesting")
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class DocumentIngestResponse(BaseModel):
    document_id: str
    document_name: str
    chunks_stored: int
    chunk_ids: list[str]
    doc_type: str
    metadata: dict[str, str | int | float]


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    page: int | None
    section: str | None
    relevance_score: float


class DocumentRagQueryResponse(BaseModel):
    query: str
    chunks: list[DocumentChunk]
    total_chunks: int
    documents_consulted: list[str]


# ---------------------------------------------------------------------------
# flashcard_generate  (used by Study Agent)
# ---------------------------------------------------------------------------

class FlashcardGenerateRequest(BaseModel):
    source: str = Field(..., min_length=10, description="Source material text to generate cards from")
    count: Annotated[int, Field(ge=1, le=100)] = 20
    level: str = Field(default="intermediate", description="Difficulty: beginner / intermediate / advanced")
    format: str = Field(default="basic", description="Card format: basic / cloze / both")
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class Flashcard(BaseModel):
    front: str
    back: str
    tags: list[str] = Field(default_factory=list)


class FlashcardGenerateResponse(BaseModel):
    cards: list[Flashcard]
    count: int
    source_summary: str
    level: str


# ---------------------------------------------------------------------------
# quiz_generate  (used by Study Agent)
# ---------------------------------------------------------------------------

class QuizGenerateRequest(BaseModel):
    source: str = Field(..., min_length=10, description="Source material text to generate quiz from")
    count: Annotated[int, Field(ge=1, le=50)] = 10
    difficulty: str = Field(default="medium", description="Difficulty: easy / medium / hard")
    question_types: list[str] = Field(default_factory=list, description="Types: multiple_choice, short_answer, fill_blank")
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class QuizQuestion(BaseModel):
    type: str  # "multiple_choice" | "short_answer" | "fill_blank"
    question: str
    options: list[str] | None = None  # for multiple_choice
    answer: str
    explanation: str | None = None


class QuizGenerateResponse(BaseModel):
    questions: list[QuizQuestion]
    count: int
    source_summary: str
    difficulty: str


# ---------------------------------------------------------------------------
# speech_to_text  (used by Voice Agent)
# ---------------------------------------------------------------------------

class SpeechToTextRequest(BaseModel):
    audio_data: str = Field(..., description="Base64-encoded audio data")
    language: str | None = Field(default=None, description="ISO 639-1 language code, e.g. 'en'")
    model: str | None = Field(default=None, description="STT model to use: 'whisper' (default) or 'deepgram'")
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class SpeechToTextResponse(BaseModel):
    text: str
    language: str | None
    confidence: float | None = None
    duration_seconds: float | None = None


# ---------------------------------------------------------------------------
# text_to_speech  (used by Voice Agent)
# ---------------------------------------------------------------------------

class TextToSpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    speed: Annotated[float, Field(ge=0.5, le=2.0)] = 1.0
    voice: str | None = Field(default=None, description="Voice ID; defaults to configured default")
    model: str | None = Field(default=None, description="TTS model: 'openai' (default), 'elevenlabs', 'polly'")
    user_id: str | None = Field(default=None, description="Stamped by the router from the authenticated user.")


class TextToSpeechResponse(BaseModel):
    audio_data: str  # base64-encoded audio
    format: str  # e.g. "mp3", "opus"
    duration_seconds: float | None = None
    model: str
