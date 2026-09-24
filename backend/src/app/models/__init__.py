"""SQLAlchemy ORM models — source of truth (replaces prior Prisma scaffold).

Models: Provider, Model, TokenUsageLog, UserPreference, User, MagicLinkToken,
        ChatSession, ChatMessage
T027: Replaces Prisma with SQLAlchemy async ORM.
"""

from __future__ import annotations

from app.auth.models import MagicLinkToken, User
from app.chat_history.models import ChatMessage
from app.models.bank_connection import BankConnection
from app.models.budget import Budget
from app.models.model import Model
from app.models.provider import Provider
from app.models.scheduled_job import ScheduledJob
from app.models.spending_alert import SpendingAlert
from app.models.token_usage import TokenUsageLog
from app.models.user_preference import UserPreference
from app.session.models import ChatSession

from app.models.subscription import (
    CreditWallet,
    Payment,
    PaymentEvent,
    PaymentMethod,
    Subscription,
    UsageLog,
)
from app.models.finance_account import FinanceAccount, FinanceAlert, FinanceTransaction
from app.models.project import Project, ProjectDocument, ProjectTask
from app.models.generated_image import GeneratedImage, UploadedMedia
from app.models.document_vault import DocumentRecord
from app.models.calendar_event import CalendarEvent
from app.models.email_message import EmailMessage
from app.models.voice_recording import VoiceRecording
from app.models.research_report import ResearchReport
from app.models.browser_task import BrowserTask
from app.models.study_deck import QuizSession, StudyCard, StudyDeck
from app.models.code_snippet import CodeExecution, CodeSnippet
from app.models.semantic_memory import CuratorRunReport, SemanticMemory
from app.models.audit_log import AuditLogEntry
from app.models.media_job import MediaAsset, MediaGenerationJob

__all__ = [
    "AuditLogEntry",
    "BankConnection",
    "BrowserTask",
    "Budget",
    "CalendarEvent",
    "ChatMessage",
    "ChatSession",
    "CodeExecution",
    "CodeSnippet",
    "CreditWallet",
    "CuratorRunReport",
    "DocumentRecord",
    "EmailMessage",
    "FinanceAccount",
    "FinanceAlert",
    "FinanceTransaction",
    "GeneratedImage",
    "MagicLinkToken",
    "MediaAsset",
    "MediaGenerationJob",
    "Model",
    "Payment",
    "PaymentEvent",
    "PaymentMethod",
    "Project",
    "ProjectDocument",
    "ProjectTask",
    "Provider",
    "QuizSession",
    "ResearchReport",
    "ScheduledJob",
    "SemanticMemory",
    "SpendingAlert",
    "StudyCard",
    "StudyDeck",
    "Subscription",
    "TokenUsageLog",
    "UploadedMedia",
    "UsageLog",
    "User",
    "UserPreference",
    "VoiceRecording",
]



