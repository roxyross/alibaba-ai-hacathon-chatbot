"""Finance repository — async ORM operations for accounts, transactions, and alerts.

Provides database access to `finance_accounts`, `finance_transactions`, and `finance_alerts`
with resilient in-memory fallback store (_MEM_*) if the database is unconfigured or unavailable.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session_factory
from app.models.finance_account import FinanceAccount, FinanceAlert, FinanceTransaction

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# In-Memory Fallback Models
# ---------------------------------------------------------------------------

@dataclass
class _MemAccount:
    id: str
    user_id: str
    account_holder: str
    institution_name: str
    account_type: str
    account_number_full: str
    account_number_masked: str
    balance_usd: float
    balance_pkr: float
    budget_limit_usd: float
    budget_limit_pkr: float
    provider: str
    status: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class _MemTransaction:
    id: str
    account_id: str
    user_id: str
    description: str
    reason: str
    category: str
    amount_usd: float
    amount_pkr: float
    transaction_type: str
    transaction_date: datetime
    is_pinned: bool = False
    metadata_json: dict[str, Any] | None = None


@dataclass
class _MemAlert:
    id: str
    user_id: str
    description: str
    alert_type: str
    threshold_usd: float | None
    threshold_pkr: float | None
    status: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_MEM_ACCOUNTS: dict[str, list[_MemAccount]] = {}
_MEM_TRANSACTIONS: dict[str, list[_MemTransaction]] = {}
_MEM_ALERTS: dict[str, list[_MemAlert]] = {}


class FinanceRepository:
    """Async repository for financial accounts, transaction ledgers, and spending alerts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory

    def _get_factory(self) -> async_sessionmaker[AsyncSession] | None:
        return self._session_factory or get_session_factory()

    # -----------------------------------------------------------------------
    # Accounts
    # -----------------------------------------------------------------------

    async def list_accounts(self, user_id: str) -> list[FinanceAccount]:
        """List all active accounts owned by the user."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(FinanceAccount)
                        .where(
                            FinanceAccount.user_id == user_id,
                            FinanceAccount.status != "disconnected",
                        )
                        .order_by(desc(FinanceAccount.created_at))
                    )
                    return list(res.scalars().all())
            except Exception as exc:
                log.warning("finance_repo.list_accounts.db_failed", error=str(exc))

        # Fallback
        mem_list = _MEM_ACCOUNTS.get(user_id, [])
        return [
            FinanceAccount(
                id=a.id,
                user_id=a.user_id,
                account_holder=a.account_holder,
                institution_name=a.institution_name,
                account_type=a.account_type,
                account_number_full=a.account_number_full,
                account_number_masked=a.account_number_masked,
                balance_usd=a.balance_usd,
                balance_pkr=a.balance_pkr,
                budget_limit_usd=a.budget_limit_usd,
                budget_limit_pkr=a.budget_limit_pkr,
                provider=a.provider,
                status=a.status,
                created_at=a.created_at,
            )
            for a in mem_list
            if a.status != "disconnected"
        ]

    async def get_account(self, account_id: str, user_id: str) -> FinanceAccount | None:
        """Get an account by ID ensuring user ownership."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(FinanceAccount).where(
                            FinanceAccount.id == account_id,
                            FinanceAccount.user_id == user_id,
                        )
                    )
                    return res.scalar_one_or_none()
            except Exception as exc:
                log.warning("finance_repo.get_account.db_failed", error=str(exc))

        mem_list = _MEM_ACCOUNTS.get(user_id, [])
        for a in mem_list:
            if a.id == account_id:
                return FinanceAccount(
                    id=a.id,
                    user_id=a.user_id,
                    account_holder=a.account_holder,
                    institution_name=a.institution_name,
                    account_type=a.account_type,
                    account_number_full=a.account_number_full,
                    account_number_masked=a.account_number_masked,
                    balance_usd=a.balance_usd,
                    balance_pkr=a.balance_pkr,
                    budget_limit_usd=a.budget_limit_usd,
                    budget_limit_pkr=a.budget_limit_pkr,
                    provider=a.provider,
                    status=a.status,
                    created_at=a.created_at,
                )
        return None

    async def create_account(
        self,
        user_id: str,
        account_holder: str,
        institution_name: str,
        account_type: str,
        account_number_full: str,
        account_number_masked: str,
        balance_usd: float,
        balance_pkr: float,
        budget_limit_usd: float = 1000.0,
        budget_limit_pkr: float = 300000.0,
        provider: str = "plaid",
        status: str = "active",
    ) -> FinanceAccount:
        """Create and persist a new financial account."""
        acc_id = f"acc_{uuid.uuid4().hex[:12]}"
        account = FinanceAccount(
            id=acc_id,
            user_id=user_id,
            account_holder=account_holder,
            institution_name=institution_name,
            account_type=account_type,
            account_number_full=account_number_full,
            account_number_masked=account_number_masked,
            balance_usd=round(balance_usd, 2),
            balance_pkr=round(balance_pkr, 2),
            budget_limit_usd=round(budget_limit_usd, 2),
            budget_limit_pkr=round(budget_limit_pkr, 2),
            provider=provider,
            status=status,
            created_at=datetime.now(UTC),
        )

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    sess.add(account)
                    await sess.commit()
                    await sess.refresh(account)
                    return account
            except Exception as exc:
                log.warning("finance_repo.create_account.db_failed", error=str(exc))

        # Always update memory store
        mem_acc = _MemAccount(
            id=acc_id,
            user_id=user_id,
            account_holder=account_holder,
            institution_name=institution_name,
            account_type=account_type,
            account_number_full=account_number_full,
            account_number_masked=account_number_masked,
            balance_usd=round(balance_usd, 2),
            balance_pkr=round(balance_pkr, 2),
            budget_limit_usd=round(budget_limit_usd, 2),
            budget_limit_pkr=round(budget_limit_pkr, 2),
            provider=provider,
            status=status,
            created_at=account.created_at,
        )
        _MEM_ACCOUNTS.setdefault(user_id, []).append(mem_acc)
        return account

    async def update_balance(
        self,
        account_id: str,
        user_id: str,
        delta_usd: float,
        delta_pkr: float,
    ) -> FinanceAccount | None:
        """Adjust account balance atomically."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(FinanceAccount).where(
                            FinanceAccount.id == account_id,
                            FinanceAccount.user_id == user_id,
                        )
                    )
                    acc = res.scalar_one_or_none()
                    if acc:
                        acc.balance_usd = round(acc.balance_usd + delta_usd, 2)
                        acc.balance_pkr = round(acc.balance_pkr + delta_pkr, 2)
                        await sess.commit()
                        await sess.refresh(acc)
                        return acc
            except Exception as exc:
                log.warning("finance_repo.update_balance.db_failed", error=str(exc))

        # Fallback
        for a in _MEM_ACCOUNTS.get(user_id, []):
            if a.id == account_id:
                a.balance_usd = round(a.balance_usd + delta_usd, 2)
                a.balance_pkr = round(a.balance_pkr + delta_pkr, 2)
                return FinanceAccount(
                    id=a.id,
                    user_id=a.user_id,
                    account_holder=a.account_holder,
                    institution_name=a.institution_name,
                    account_type=a.account_type,
                    account_number_full=a.account_number_full,
                    account_number_masked=a.account_number_masked,
                    balance_usd=a.balance_usd,
                    balance_pkr=a.balance_pkr,
                    budget_limit_usd=a.budget_limit_usd,
                    budget_limit_pkr=a.budget_limit_pkr,
                    provider=a.provider,
                    status=a.status,
                    created_at=a.created_at,
                )
        return None

    async def delete_account(self, account_id: str, user_id: str) -> bool:
        """Delete an account and cascade delete its transactions."""
        factory = self._get_factory()
        deleted = False
        if factory is not None:
            try:
                async with factory() as sess:
                    del_res = await sess.execute(
                        delete(FinanceAccount).where(
                            FinanceAccount.id == account_id,
                            FinanceAccount.user_id == user_id,
                        )
                    )
                    rowcount = getattr(del_res, "rowcount", None) or 0
                    if rowcount > 0:
                        deleted = True
                    await sess.commit()
            except Exception as exc:
                log.warning("finance_repo.delete_account.db_failed", error=str(exc))

        # Update memory store
        if user_id in _MEM_ACCOUNTS:
            before_len = len(_MEM_ACCOUNTS[user_id])
            _MEM_ACCOUNTS[user_id] = [a for a in _MEM_ACCOUNTS[user_id] if a.id != account_id]
            if len(_MEM_ACCOUNTS[user_id]) < before_len:
                deleted = True

        if user_id in _MEM_TRANSACTIONS:
            _MEM_TRANSACTIONS[user_id] = [t for t in _MEM_TRANSACTIONS[user_id] if t.account_id != account_id]

        return deleted

    # -----------------------------------------------------------------------
    # Transactions
    # -----------------------------------------------------------------------

    async def list_transactions(
        self,
        user_id: str,
        account_id: str | None = None,
        period: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
    ) -> list[FinanceTransaction]:
        """List transactions with period filtering and sorting."""
        now = datetime.now(UTC)
        filter_start: datetime | None = None

        if period == "day":
            filter_start = now - timedelta(days=1)
        elif period == "week":
            filter_start = now - timedelta(days=7)
        elif period == "month":
            filter_start = now - timedelta(days=30)
        elif period == "year":
            filter_start = now - timedelta(days=365)
        elif start_date:
            with contextlib.suppress(ValueError):
                filter_start = datetime.fromisoformat(start_date).replace(tzinfo=UTC)

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    query = select(FinanceTransaction).where(FinanceTransaction.user_id == user_id)
                    if account_id:
                        query = query.where(FinanceTransaction.account_id == account_id)
                    if filter_start:
                        query = query.where(FinanceTransaction.transaction_date >= filter_start)

                    query = query.order_by(desc(FinanceTransaction.transaction_date)).limit(limit)
                    res = await sess.execute(query)
                    return list(res.scalars().all())
            except Exception as exc:
                log.warning("finance_repo.list_transactions.db_failed", error=str(exc))

        # Fallback
        txs = _MEM_TRANSACTIONS.get(user_id, [])
        filtered: list[_MemTransaction] = []
        for t in txs:
            if account_id and t.account_id != account_id:
                continue
            if filter_start and t.transaction_date < filter_start:
                continue
            filtered.append(t)

        filtered.sort(key=lambda x: x.transaction_date, reverse=True)
        return [
            FinanceTransaction(
                id=t.id,
                account_id=t.account_id,
                user_id=t.user_id,
                description=t.description,
                reason=t.reason,
                category=t.category,
                amount_usd=t.amount_usd,
                amount_pkr=t.amount_pkr,
                transaction_type=t.transaction_type,
                transaction_date=t.transaction_date,
                is_pinned=t.is_pinned,
                metadata_json=t.metadata_json,
            )
            for t in filtered[:limit]
        ]

    async def create_transaction(
        self,
        user_id: str,
        account_id: str,
        description: str,
        reason: str,
        category: str,
        amount_usd: float,
        amount_pkr: float,
        transaction_type: str = "debit",
        transaction_date: datetime | None = None,
        is_pinned: bool = False,
        metadata_json: dict[str, Any] | None = None,
    ) -> FinanceTransaction:
        """Insert a transaction record."""
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        dt = transaction_date or datetime.now(UTC)
        tx = FinanceTransaction(
            id=tx_id,
            account_id=account_id,
            user_id=user_id,
            description=description,
            reason=reason,
            category=category,
            amount_usd=round(amount_usd, 2),
            amount_pkr=round(amount_pkr, 2),
            transaction_type=transaction_type,
            transaction_date=dt,
            is_pinned=is_pinned,
            metadata_json=metadata_json,
        )

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    sess.add(tx)
                    await sess.commit()
                    await sess.refresh(tx)
                    return tx
            except Exception as exc:
                log.warning("finance_repo.create_transaction.db_failed", error=str(exc))

        mem_tx = _MemTransaction(
            id=tx_id,
            account_id=account_id,
            user_id=user_id,
            description=description,
            reason=reason,
            category=category,
            amount_usd=round(amount_usd, 2),
            amount_pkr=round(amount_pkr, 2),
            transaction_type=transaction_type,
            transaction_date=dt,
            is_pinned=is_pinned,
            metadata_json=metadata_json,
        )
        _MEM_TRANSACTIONS.setdefault(user_id, []).append(mem_tx)
        return tx

    async def toggle_pin_transaction(self, tx_id: str, user_id: str) -> FinanceTransaction | None:
        """Toggle is_pinned on a transaction."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(FinanceTransaction).where(
                            FinanceTransaction.id == tx_id,
                            FinanceTransaction.user_id == user_id,
                        )
                    )
                    tx = res.scalar_one_or_none()
                    if tx:
                        tx.is_pinned = not tx.is_pinned
                        await sess.commit()
                        await sess.refresh(tx)
                        return tx
            except Exception as exc:
                log.warning("finance_repo.toggle_pin.db_failed", error=str(exc))

        for t in _MEM_TRANSACTIONS.get(user_id, []):
            if t.id == tx_id:
                t.is_pinned = not t.is_pinned
                return FinanceTransaction(
                    id=t.id,
                    account_id=t.account_id,
                    user_id=t.user_id,
                    description=t.description,
                    reason=t.reason,
                    category=t.category,
                    amount_usd=t.amount_usd,
                    amount_pkr=t.amount_pkr,
                    transaction_type=t.transaction_type,
                    transaction_date=t.transaction_date,
                    is_pinned=t.is_pinned,
                    metadata_json=t.metadata_json,
                )
        return None

    # -----------------------------------------------------------------------
    # Alerts
    # -----------------------------------------------------------------------

    async def list_alerts(self, user_id: str) -> list[FinanceAlert]:
        """List all spending/budget alerts for a user."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(FinanceAlert)
                        .where(FinanceAlert.user_id == user_id)
                        .order_by(desc(FinanceAlert.created_at))
                    )
                    return list(res.scalars().all())
            except Exception as exc:
                log.warning("finance_repo.list_alerts.db_failed", error=str(exc))

        return [
            FinanceAlert(
                id=a.id,
                user_id=a.user_id,
                description=a.description,
                alert_type=a.alert_type,
                threshold_usd=a.threshold_usd,
                threshold_pkr=a.threshold_pkr,
                status=a.status,
                created_at=a.created_at,
            )
            for a in _MEM_ALERTS.get(user_id, [])
        ]

    async def create_alert(
        self,
        user_id: str,
        description: str,
        alert_type: str = "budget_warning",
        threshold_usd: float | None = None,
        threshold_pkr: float | None = None,
        status: str = "active",
    ) -> FinanceAlert:
        """Create a new alert."""
        al_id = f"al_{uuid.uuid4().hex[:12]}"
        al = FinanceAlert(
            id=al_id,
            user_id=user_id,
            description=description,
            alert_type=alert_type,
            threshold_usd=threshold_usd,
            threshold_pkr=threshold_pkr,
            status=status,
            created_at=datetime.now(UTC),
        )

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    sess.add(al)
                    await sess.commit()
                    await sess.refresh(al)
                    return al
            except Exception as exc:
                log.warning("finance_repo.create_alert.db_failed", error=str(exc))

        _MEM_ALERTS.setdefault(user_id, []).append(
            _MemAlert(
                id=al_id,
                user_id=user_id,
                description=description,
                alert_type=alert_type,
                threshold_usd=threshold_usd,
                threshold_pkr=threshold_pkr,
                status=status,
                created_at=al.created_at,
            )
        )
        return al

    async def toggle_alert_status(self, alert_id: str, user_id: str) -> FinanceAlert | None:
        """Toggle alert status between 'active' and 'paused'."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(FinanceAlert).where(
                            FinanceAlert.id == alert_id,
                            FinanceAlert.user_id == user_id,
                        )
                    )
                    al = res.scalar_one_or_none()
                    if al:
                        al.status = "paused" if al.status == "active" else "active"
                        await sess.commit()
                        await sess.refresh(al)
                        return al
            except Exception as exc:
                log.warning("finance_repo.toggle_alert.db_failed", error=str(exc))

        for a in _MEM_ALERTS.get(user_id, []):
            if a.id == alert_id:
                a.status = "paused" if a.status == "active" else "active"
                return FinanceAlert(
                    id=a.id,
                    user_id=a.user_id,
                    description=a.description,
                    alert_type=a.alert_type,
                    threshold_usd=a.threshold_usd,
                    threshold_pkr=a.threshold_pkr,
                    status=a.status,
                    created_at=a.created_at,
                )
        return None

    async def delete_alert(self, alert_id: str, user_id: str) -> bool:
        """Delete an alert."""
        factory = self._get_factory()
        deleted = False
        if factory is not None:
            try:
                async with factory() as sess:
                    del_res = await sess.execute(
                        delete(FinanceAlert).where(
                            FinanceAlert.id == alert_id,
                            FinanceAlert.user_id == user_id,
                        )
                    )
                    rowcount = getattr(del_res, "rowcount", None) or 0
                    if rowcount > 0:
                        deleted = True
                    await sess.commit()
            except Exception as exc:
                log.warning("finance_repo.delete_alert.db_failed", error=str(exc))

        if user_id in _MEM_ALERTS:
            before_len = len(_MEM_ALERTS[user_id])
            _MEM_ALERTS[user_id] = [a for a in _MEM_ALERTS[user_id] if a.id != alert_id]
            if len(_MEM_ALERTS[user_id]) < before_len:
                deleted = True

        return deleted
