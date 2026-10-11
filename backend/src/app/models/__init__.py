"""SQLAlchemy ORM models — source of truth (replaces prior Prisma scaffold).

Models: Provider, Model, TokenUsageLog, UserPreference, User, MagicLinkToken,
        ChatSession, ChatMessage
T027: Replaces Prisma with SQLAlchemy async ORM.
"""

from __future__ import annotations

from app.auth.models import MagicLinkToken, User
from app.chat_history.models import ChatMessage
from app.models.agent_runtime import AgentAction, AgentStep, AgentTask, PermissionGrant
from app.models.artifact import CoworkArtifact, CoworkArtifactVersion
from app.models.audit_log import AuditLogEntry
from app.models.bank_connection import BankConnection
from app.models.browser_task import BrowserTask
from app.models.budget import Budget
from app.models.calendar_event import CalendarEvent
from app.models.code_snippet import CodeExecution, CodeSnippet
from app.models.connector import ConnectorInstance
from app.models.custom_skill import CustomSkill
from app.models.device import (
    DeviceActionLog,
    DeviceCommand,
    DeviceEnrollmentToken,
    DeviceRegistration,
    DiscoveredApp,
)
from app.models.document_vault import DocumentChunkRecord, DocumentRecord
from app.models.email_message import EmailMessage
from app.models.finance_account import FinanceAccount, FinanceAlert, FinanceTransaction
from app.models.generated_image import GeneratedImage, UploadedMedia
from app.models.mcp import MCPServerConfig
from app.models.media_job import MediaAsset, MediaGenerationJob
from app.models.model import Model
from app.models.project import Project, ProjectDocument, ProjectTask
from app.models.provider import Provider
from app.models.research_report import ResearchReport
from app.models.scheduled_job import ScheduledJob
from app.models.semantic_memory import CuratorRunReport, SemanticMemory
from app.models.spending_alert import SpendingAlert
from app.models.study_deck import QuizSession, StudyCard, StudyDeck
from app.models.subscription import (
    CreditWallet,
    Payment,
    PaymentEvent,
    PaymentMethod,
    Subscription,
    UsageLog,
)
from app.models.token_usage import TokenUsageLog
from app.models.trust import (
    DataExportJob,
    EvaluationRecord,
    PersonalizationProposal,
    RecoveryJob,
    TrustEvent,
)
from app.models.user_preference import UserPreference
from app.models.voice_recording import VoiceRecording
from app.session.models import ChatSession

__all__ = [
    "AgentAction",
    "AgentStep",
    "AgentTask",
    "AuditLogEntry",
    "BankConnection",
    "BrowserTask",
    "Budget",
    "CalendarEvent",
    "ChatMessage",
    "ChatSession",
    "CodeExecution",
    "CodeSnippet",
    "ConnectorInstance",
    "CoworkArtifact",
    "CoworkArtifactVersion",
    "CreditWallet",
    "CuratorRunReport",
    "CustomSkill",
    "DataExportJob",
    "DeviceActionLog",
    "DeviceCommand",
    "DeviceEnrollmentToken",
    "DeviceRegistration",
    "DiscoveredApp",
    "DocumentChunkRecord",
    "DocumentRecord",
    "EmailMessage",
    "EvaluationRecord",
    "FinanceAccount",
    "FinanceAlert",
    "FinanceTransaction",
    "GeneratedImage",
    "MagicLinkToken",
    "MCPServerConfig",
    "MediaAsset",
    "MediaGenerationJob",
    "Model",
    "Payment",
    "PaymentEvent",
    "PaymentMethod",
    "PermissionGrant",
    "PersonalizationProposal",
    "Project",
    "ProjectDocument",
    "ProjectTask",
    "Provider",
    "QuizSession",
    "RecoveryJob",
    "ResearchReport",
    "ScheduledJob",
    "SemanticMemory",
    "SpendingAlert",
    "StudyCard",
    "StudyDeck",
    "Subscription",
    "TokenUsageLog",
    "TrustEvent",
    "UploadedMedia",
    "UsageLog",
    "User",
    "UserPreference",
    "VoiceRecording",
]



