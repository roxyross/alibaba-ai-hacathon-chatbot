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
from app.models.spending_alert import SpendingAlert
from app.models.token_usage import TokenUsageLog
from app.models.user_preference import UserPreference
from app.session.models import ChatSession

__all__ = [
    "BankConnection",
    "Budget",
    "ChatMessage",
    "ChatSession",
    "MagicLinkToken",
    "Model",
    "Provider",
    "SpendingAlert",
    "TokenUsageLog",
    "User",
    "UserPreference",
]
