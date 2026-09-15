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

from app.models.subscription import CreditWallet, PaymentMethod, Subscription, UsageLog
from app.models.finance_account import FinanceAccount, FinanceAlert, FinanceTransaction
from app.models.project import Project
from app.models.generated_image import GeneratedImage
from app.models.document_vault import DocumentRecord

__all__ = [
    "BankConnection",
    "Budget",
    "ChatMessage",
    "ChatSession",
    "CreditWallet",
    "DocumentRecord",
    "FinanceAccount",
    "FinanceAlert",
    "FinanceTransaction",
    "GeneratedImage",
    "MagicLinkToken",
    "Model",
    "PaymentMethod",
    "Project",
    "Provider",
    "ScheduledJob",
    "SpendingAlert",
    "Subscription",
    "TokenUsageLog",
    "UsageLog",
    "User",
    "UserPreference",
]
