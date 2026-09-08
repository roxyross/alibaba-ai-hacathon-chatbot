"""Pydantic input schemas for runtime skill validation.

Each skill registered with SkillExecutor.register() passes its input schema here.
SkillExecutor.invoke() validates the incoming inputs dict against the schema
BEFORE calling the skill function — converting LLM-emitted strings to correct
types and surfacing a clean SkillResult error (not a raw TypeError) when
validation fails.

Schema field names MUST match the target skill function's parameter names
exactly (after the leading `user_id` keyword-only param).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

class WebSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    num_results: int = Field(default=5, ge=1, le=20)
    source: str | None = Field(
        default=None,
        description="Search provider: 'tavily' or 'google'. Defaults to tavily if TAVILY_API_KEY is set, else google.",
    )


# ---------------------------------------------------------------------------
# store_memory
# ---------------------------------------------------------------------------

class StoreMemoryInput(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    importance: str = Field(default="normal")  # "low" | "normal" | "forever"
    tags: list[str] | None = None
    permanent: bool = Field(default=False)


# ---------------------------------------------------------------------------
# retrieve_memory
# ---------------------------------------------------------------------------

class RetrieveMemoryInput(BaseModel):
    query: str | None = None
    limit: int = Field(default=20, ge=1, le=50)
    importance: str | None = None
    include_soft_deleted: bool = Field(default=False)


# ---------------------------------------------------------------------------
# calendar_read
# ---------------------------------------------------------------------------

class CalendarReadInput(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    max_events: int = Field(default=50, ge=1, le=200)
    calendar_id: str = Field(default="primary")


# ---------------------------------------------------------------------------
# calculator
# ---------------------------------------------------------------------------

class CalculatorInput(BaseModel):
    expression: str = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# email_draft
# ---------------------------------------------------------------------------

class EmailDraftInput(BaseModel):
    to: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)
    cc: list[str] | None = None
    bcc: list[str] | None = None


# ---------------------------------------------------------------------------
# browser_navigate
# ---------------------------------------------------------------------------

class BrowserNavigateInput(BaseModel):
    url: str = Field(..., min_length=1)
    actions: list[dict] | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=120)
    extract_selectors: dict | None = None


# ---------------------------------------------------------------------------
# browser_fill_form
# ---------------------------------------------------------------------------

class BrowserFillFormInput(BaseModel):
    url: str = Field(..., min_length=1)
    fields: dict[str, str] = Field(..., min_length=1)
    submit: bool = Field(default=False)
    screenshot: bool = Field(default=True)
    timeout_seconds: int = Field(default=60, ge=1, le=120)


# ---------------------------------------------------------------------------
# schedule_job
# ---------------------------------------------------------------------------

class ScheduleJobInput(BaseModel):
    op: str = Field(...)  # "create" | "update" | "list" | "cancel" | "pause" | "resume"
    job_id: str | None = None
    name: str | None = None
    schedule: str | None = None
    timezone: str = Field(default="UTC")
    action: dict | None = None
    confirm_on_fire: bool = Field(default=False)
    tag: str | None = None


# ---------------------------------------------------------------------------
# task_breakdown
# ---------------------------------------------------------------------------

class TaskBreakdownInput(BaseModel):
    goal: str = Field(..., min_length=1)
    context: str | None = None
    horizon: str = Field(default="normal")


# ---------------------------------------------------------------------------
# code_generate
# ---------------------------------------------------------------------------

class CodeGenerateInput(BaseModel):
    task: str = Field(..., min_length=1)
    language: str | None = None
    context_files: list[str] | None = None
    constraints: list[str] | None = None
    output_path: str | None = None


# ---------------------------------------------------------------------------
# code_explain
# ---------------------------------------------------------------------------

class CodeExplainInput(BaseModel):
    code: str = Field(..., min_length=1)
    language: str | None = None
    level: str = Field(default="auto")


# ---------------------------------------------------------------------------
# code_debug
# ---------------------------------------------------------------------------

class CodeDebugInput(BaseModel):
    code: str = Field(..., min_length=1)
    error_message: str | None = None
    language: str = Field(default="python")


# ---------------------------------------------------------------------------
# document_rag_query
# ---------------------------------------------------------------------------

class DocumentRagQueryInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    document_ids: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# document_ingest
# ---------------------------------------------------------------------------

class DocumentIngestInput(BaseModel):
    document_id: str | None = None
    document_name: str | None = None
    text: str | None = None
    replace_existing: bool = Field(default=False)


# ---------------------------------------------------------------------------
# flashcard_generate
# ---------------------------------------------------------------------------

class FlashcardGenerateInput(BaseModel):
    source: str = Field(..., min_length=1)
    count: int = Field(default=20, ge=1, le=50)
    level: str = Field(default="intermediate")
    format: str = Field(default="qa")
    existing_deck_id: str | None = None


# ---------------------------------------------------------------------------
# quiz_generate
# ---------------------------------------------------------------------------

class QuizGenerateInput(BaseModel):
    source: str = Field(..., min_length=1)
    count: int = Field(default=10, ge=1, le=20)
    types: list[str] | None = None
    difficulty: str = Field(default="medium")


# ---------------------------------------------------------------------------
# speech_to_text
# ---------------------------------------------------------------------------

class SpeechToTextInput(BaseModel):
    audio_data: str | None = None
    session_id: str | None = None
    language: str | None = None
    interim: bool = Field(default=False)
    sample_rate: int = Field(default=16000)


# ---------------------------------------------------------------------------
# text_to_speech
# ---------------------------------------------------------------------------

class TextToSpeechInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    format: str = Field(default="mp3")
    language_code: str | None = None


# ---------------------------------------------------------------------------
# email_send (sensitive — requires explicit user confirmation)
# ---------------------------------------------------------------------------

class EmailSendInput(BaseModel):
    to: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)
    cc: list[str] | None = None
    bcc: list[str] | None = None


# ---------------------------------------------------------------------------
# bank_connect (sensitive — requires explicit user confirmation)
# ---------------------------------------------------------------------------

class BankConnectInput(BaseModel):
    op: str = Field(...)  # "connect" | "exchange" | "list_accounts" | "get_transactions" | "get_balance" | "disconnect"
    institution: str | None = None
    access_token: str | None = None
    public_token: str | None = None
    account_ids: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None


# ---------------------------------------------------------------------------
# critic_review
# ---------------------------------------------------------------------------

class CriticReviewInput(BaseModel):
    content: str = Field(..., min_length=1)
    type: str = Field(default="text")  # "text" | "code" | "plan" | "decision" | "research"
    depth: str = Field(default="standard")  # "quick" | "standard" | "deep"
    criteria: list[str] | None = None
