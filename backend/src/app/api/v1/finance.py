"""FastAPI router for Finance API — accounts, budgets, spending alerts, and financial summaries.

Backed by live NeonDB PostgreSQL tables (finance_accounts, finance_transactions, finance_alerts,
budgets) and FinanceRepository, enforcing strict multi-tenant isolation and dual-currency support.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_session_factory
from app.finance.repository import FinanceRepository
from app.models.budget import Budget
from app.models.spending_alert import SpendingAlert

log = structlog.get_logger()

router = APIRouter(prefix="/finance", tags=["finance"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

# Budget schemas

class BudgetCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    monthly_limit: float = Field(..., gt=0)
    alert_threshold: float = Field(default=0.8, ge=0.1, le=1.0)


class BudgetUpdate(BaseModel):
    category: str | None = Field(default=None, max_length=100)
    monthly_limit: float | None = Field(default=None, gt=0)
    alert_threshold: float | None = Field(default=None, ge=0.1, le=1.0)


class BudgetResponse(BaseModel):
    id: str
    category: str
    monthly_limit: float
    alert_threshold: float
    current_spent: float
    pct_used: float
    created_at: datetime

    @classmethod
    def from_orm(cls, b: Budget) -> BudgetResponse:
        pct = (b.current_spent / b.monthly_limit * 100) if b.monthly_limit > 0 else 0.0
        return cls(
            id=b.id,
            category=b.category,
            monthly_limit=b.monthly_limit,
            alert_threshold=b.alert_threshold,
            current_spent=b.current_spent,
            pct_used=round(pct, 1),
            created_at=b.created_at,
        )


class BudgetListResponse(BaseModel):
    budgets: list[BudgetResponse]


# Spending alert schemas

class AlertCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    alert_type: str = Field(
        ..., pattern="^(over_budget|unusual_charge|bill_reminder|budget_warning)$"
    )
    threshold_amount: float | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, max_length=100)
    institution: str | None = Field(default=None, max_length=200)
    enabled: bool = Field(default=True)


class AlertResponse(BaseModel):
    id: str
    name: str
    alert_type: str
    threshold_amount: float | None
    category: str | None
    institution: str | None
    enabled: bool
    status: str
    last_triggered_at: datetime | None
    created_at: datetime

    @classmethod
    def from_orm(cls, a: SpendingAlert) -> AlertResponse:
        return cls(
            id=a.id,
            name=a.name,
            alert_type=a.alert_type,
            threshold_amount=a.threshold_amount,
            category=a.category,
            institution=a.institution,
            enabled=a.enabled,
            status="Active" if a.enabled else "Pause",
            last_triggered_at=a.last_triggered_at,
            created_at=a.created_at,
        )


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse]


# Transaction schemas

class TransactionCreate(BaseModel):
    account_id: str
    description: str = Field(..., min_length=1, max_length=255)
    reason: str = "Operational expense"
    category: str = "General"
    amount_usd: float
    amount_pkr: float | None = None
    transaction_type: str = "debit"
    is_pinned: bool = False


class TransactionResponse(BaseModel):
    id: str
    account_id: str
    date: str
    time: str = ""
    description: str
    reason: str = ""
    amount: float
    amount_usd: float
    amount_pkr: float
    category: str
    pending: bool = False
    is_pinned: bool = False
    transaction_type: str = "debit"


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int


# Account & Summary schemas

class AccountSummary(BaseModel):
    connection_id: str
    institution: str | None
    account_id: str
    name: str
    type: str
    mask: str | None
    balance: float | None
    balance_usd: float
    balance_pkr: float
    budget_usd: float
    budget_pkr: float
    provider: str


class FinanceSummary(BaseModel):
    accounts: list[AccountSummary]
    total_balance: float
    total_balance_usd: float
    total_balance_pkr: float
    budgets: list[BudgetResponse]
    alerts: list[AlertResponse]
    month_spending: float
    month_spending_usd: float
    month_spending_pkr: float


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_factory_or_503() -> async_sessionmaker[AsyncSession]:
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured",
        )
    return factory


# ---------------------------------------------------------------------------
# GET /finance/summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=FinanceSummary)
async def get_finance_summary(
    current_user: User = Depends(get_current_user),
) -> FinanceSummary:
    """Return a full financial snapshot: accounts, budgets, alerts, month spending."""
    user_id = str(current_user.id)
    repo = FinanceRepository()

    # 1. Fetch user accounts from FinanceRepository
    db_accounts = await repo.list_accounts(user_id)
    accounts: list[AccountSummary] = [
        AccountSummary(
            connection_id=a.id,
            institution=a.institution_name,
            account_id=a.id,
            name=f"{a.institution_name} {a.account_holder}",
            type=a.account_type,
            mask=a.account_number_masked[-4:] if len(a.account_number_masked) >= 4 else a.account_number_masked,
            balance=a.balance_usd,
            balance_usd=a.balance_usd,
            balance_pkr=a.balance_pkr,
            budget_usd=a.budget_limit_usd,
            budget_pkr=a.budget_limit_pkr,
            provider=a.provider,
        )
        for a in db_accounts
    ]

    total_balance_usd = sum(a.balance_usd for a in accounts)
    total_balance_pkr = sum(a.balance_pkr for a in accounts)

    # 2. Fetch budgets
    factory = get_session_factory()
    budgets: list[BudgetResponse] = []
    if factory is not None:
        try:
            async with factory() as sess:
                budgets_res = await sess.execute(
                    select(Budget).where(Budget.user_id == user_id)
                )
                budgets_orm = budgets_res.scalars().all()
                budgets = [BudgetResponse.from_orm(b) for b in budgets_orm]
        except Exception as exc:
            log.warning("finance.summary.budgets_failed", error=str(exc))

    # 3. Fetch alerts
    alerts: list[AlertResponse] = []
    if factory is not None:
        try:
            async with factory() as sess:
                alerts_res = await sess.execute(
                    select(SpendingAlert).where(SpendingAlert.user_id == user_id)
                )
                alerts_orm = alerts_res.scalars().all()
                alerts = [AlertResponse.from_orm(a) for a in alerts_orm]
        except Exception as exc:
            log.warning("finance.summary.alerts_failed", error=str(exc))

    # Also check repo alerts if SQL returned none
    if not alerts:
        repo_alerts = await repo.list_alerts(user_id)
        alerts = [
            AlertResponse(
                id=al.id,
                name=al.description,
                alert_type=al.alert_type,
                threshold_amount=al.threshold_usd,
                category=None,
                institution=None,
                enabled=(al.status == "active"),
                status="Active" if al.status == "active" else "Pause",
                last_triggered_at=None,
                created_at=al.created_at,
            )
            for al in repo_alerts
        ]

    # 4. Compute month spending from real transactions in repository
    month_txs = await repo.list_transactions(user_id=user_id, period="month", limit=500)
    month_spending_usd = sum(abs(t.amount_usd) for t in month_txs if t.amount_usd < 0)
    month_spending_pkr = sum(abs(t.amount_pkr) for t in month_txs if t.amount_pkr < 0)

    return FinanceSummary(
        accounts=accounts,
        total_balance=round(total_balance_usd, 2),
        total_balance_usd=round(total_balance_usd, 2),
        total_balance_pkr=round(total_balance_pkr, 2),
        budgets=budgets,
        alerts=alerts,
        month_spending=round(month_spending_usd, 2),
        month_spending_usd=round(month_spending_usd, 2),
        month_spending_pkr=round(month_spending_pkr, 2),
    )


# ---------------------------------------------------------------------------
# GET /finance/transactions
# ---------------------------------------------------------------------------

@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = Query(default=None, pattern="^(day|week|month|year)$"),
    limit: int = 100,
    current_user: User = Depends(get_current_user),
) -> TransactionListResponse:
    """Fetch transactions with statement period filtering from FinanceRepository."""
    user_id = str(current_user.id)
    repo = FinanceRepository()
    txs = await repo.list_transactions(
        user_id=user_id,
        period=period,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    response_items: list[TransactionResponse] = []
    for t in txs:
        d_str = t.transaction_date.strftime("%Y-%m-%d") if t.transaction_date else ""
        t_str = t.transaction_date.strftime("%H:%M:%S") if t.transaction_date else ""
        response_items.append(
            TransactionResponse(
                id=t.id,
                account_id=t.account_id,
                date=d_str,
                time=t_str,
                description=t.description,
                reason=t.reason,
                amount=t.amount_usd,
                amount_usd=t.amount_usd,
                amount_pkr=t.amount_pkr,
                category=t.category,
                pending=False,
                is_pinned=t.is_pinned,
                transaction_type=t.transaction_type,
            )
        )

    return TransactionListResponse(
        transactions=response_items,
        total=len(response_items),
    )


@router.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    body: TransactionCreate,
    current_user: User = Depends(get_current_user),
) -> TransactionResponse:
    """Manually add or sync a transaction into the user's ledger."""
    user_id = str(current_user.id)
    repo = FinanceRepository()

    # Validate account ownership
    acc = await repo.get_account(body.account_id, user_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    amount_pkr = body.amount_pkr if body.amount_pkr is not None else round(body.amount_usd * 300.0, 2)
    tx = await repo.create_transaction(
        user_id=user_id,
        account_id=body.account_id,
        description=body.description,
        reason=body.reason,
        category=body.category,
        amount_usd=body.amount_usd,
        amount_pkr=amount_pkr,
        transaction_type=body.transaction_type,
        is_pinned=body.is_pinned,
    )

    # Adjust account balance
    await repo.update_balance(
        account_id=body.account_id,
        user_id=user_id,
        delta_usd=body.amount_usd,
        delta_pkr=amount_pkr,
    )

    d_str = tx.transaction_date.strftime("%Y-%m-%d") if tx.transaction_date else ""
    t_str = tx.transaction_date.strftime("%H:%M:%S") if tx.transaction_date else ""
    return TransactionResponse(
        id=tx.id,
        account_id=tx.account_id,
        date=d_str,
        time=t_str,
        description=tx.description,
        reason=tx.reason,
        amount=tx.amount_usd,
        amount_usd=tx.amount_usd,
        amount_pkr=tx.amount_pkr,
        category=tx.category,
        pending=False,
        is_pinned=tx.is_pinned,
        transaction_type=tx.transaction_type,
    )


@router.patch("/transactions/{transaction_id}/pin", response_model=TransactionResponse)
async def toggle_pin_transaction(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
) -> TransactionResponse:
    """Toggle the is_pinned status on a transaction."""
    user_id = str(current_user.id)
    repo = FinanceRepository()
    updated_tx = await repo.toggle_pin_transaction(transaction_id, user_id)
    if not updated_tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    d_str = updated_tx.transaction_date.strftime("%Y-%m-%d") if updated_tx.transaction_date else ""
    t_str = updated_tx.transaction_date.strftime("%H:%M:%S") if updated_tx.transaction_date else ""
    return TransactionResponse(
        id=updated_tx.id,
        account_id=updated_tx.account_id,
        date=d_str,
        time=t_str,
        description=updated_tx.description,
        reason=updated_tx.reason,
        amount=updated_tx.amount_usd,
        amount_usd=updated_tx.amount_usd,
        amount_pkr=updated_tx.amount_pkr,
        category=updated_tx.category,
        pending=False,
        is_pinned=updated_tx.is_pinned,
        transaction_type=updated_tx.transaction_type,
    )


# ---------------------------------------------------------------------------
# Account Management
# ---------------------------------------------------------------------------

@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_finance_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Disconnect and delete a financial account."""
    user_id = str(current_user.id)
    repo = FinanceRepository()
    acc = await repo.get_account(account_id, user_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    deleted = await repo.delete_account(account_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Budget CRUD
# ---------------------------------------------------------------------------

@router.get("/budgets", response_model=BudgetListResponse)
async def list_budgets(
    current_user: User = Depends(get_current_user),
) -> BudgetListResponse:
    """List all budgets for the authenticated user."""
    factory = get_session_factory()
    if factory is None:
        return BudgetListResponse(budgets=[])
    async with factory() as sess:
        result = await sess.execute(
            select(Budget).where(Budget.user_id == str(current_user.id))
        )
        budgets = result.scalars().all()
    return BudgetListResponse(budgets=[BudgetResponse.from_orm(b) for b in budgets])


@router.post("/budgets", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    body: BudgetCreate,
    current_user: User = Depends(get_current_user),
) -> BudgetResponse:
    """Create a new monthly budget for a spending category."""
    factory = _get_factory_or_503()
    budget = Budget(
        user_id=str(current_user.id),
        category=body.category,
        monthly_limit=body.monthly_limit,
        alert_threshold=body.alert_threshold,
    )
    async with factory() as sess:
        sess.add(budget)
        await sess.commit()
        await sess.refresh(budget)
    log.info("finance.budget.created", user_id=str(current_user.id), category=body.category)
    return BudgetResponse.from_orm(budget)


@router.put("/budgets/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: str,
    body: BudgetUpdate,
    current_user: User = Depends(get_current_user),
) -> BudgetResponse:
    """Update an existing budget."""
    factory = _get_factory_or_503()
    async with factory() as sess:
        result = await sess.execute(
            select(Budget).where(
                Budget.id == budget_id,
                Budget.user_id == str(current_user.id),
            )
        )
        budget = result.scalar_one_or_none()
        if not budget:
            raise HTTPException(status_code=404, detail="Budget not found")

        if body.category is not None:
            budget.category = body.category
        if body.monthly_limit is not None:
            budget.monthly_limit = body.monthly_limit
        if body.alert_threshold is not None:
            budget.alert_threshold = body.alert_threshold
        budget.updated_at = datetime.now(UTC)

        await sess.commit()
        await sess.refresh(budget)

    log.info("finance.budget.updated", user_id=str(current_user.id), budget_id=budget_id)
    return BudgetResponse.from_orm(budget)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_budget(
    budget_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a budget."""
    factory = _get_factory_or_503()
    async with factory() as sess:
        del_res = cast(
            CursorResult[Any],
            await sess.execute(
                delete(Budget).where(
                    Budget.id == budget_id,
                    Budget.user_id == str(current_user.id),
                )
            ),
        )
        rowcount = getattr(del_res, "rowcount", None) or 0
        if rowcount == 0:
            raise HTTPException(status_code=404, detail="Budget not found")
        await sess.commit()
    log.info("finance.budget.deleted", user_id=str(current_user.id), budget_id=budget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Spending Alert CRUD
# ---------------------------------------------------------------------------

@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    current_user: User = Depends(get_current_user),
) -> AlertListResponse:
    """List all spending alerts for the authenticated user."""
    factory = get_session_factory()
    alerts: list[AlertResponse] = []
    if factory is not None:
        try:
            async with factory() as sess:
                result = await sess.execute(
                    select(SpendingAlert).where(SpendingAlert.user_id == str(current_user.id))
                )
                alerts = [AlertResponse.from_orm(a) for a in result.scalars().all()]
        except Exception as exc:
            log.warning("finance.alerts.fetch_failed", error=str(exc))

    if not alerts:
        repo = FinanceRepository()
        repo_alerts = await repo.list_alerts(str(current_user.id))
        alerts = [
            AlertResponse(
                id=al.id,
                name=al.description,
                alert_type=al.alert_type,
                threshold_amount=al.threshold_usd,
                category=None,
                institution=None,
                enabled=(al.status == "active"),
                status="Active" if al.status == "active" else "Pause",
                last_triggered_at=None,
                created_at=al.created_at,
            )
            for al in repo_alerts
        ]

    return AlertListResponse(alerts=alerts)


@router.post("/alerts", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    current_user: User = Depends(get_current_user),
) -> AlertResponse:
    """Create a new spending alert."""
    user_id = str(current_user.id)
    factory = get_session_factory()
    if factory is not None:
        try:
            alert = SpendingAlert(
                user_id=user_id,
                name=body.name,
                alert_type=body.alert_type,
                threshold_amount=body.threshold_amount,
                category=body.category,
                institution=body.institution,
                enabled=body.enabled,
            )
            async with factory() as sess:
                sess.add(alert)
                await sess.commit()
                await sess.refresh(alert)
            log.info("finance.alert.created", user_id=user_id, name=body.name)
            return AlertResponse.from_orm(alert)
        except Exception as exc:
            log.warning("finance.alert.create_db_failed", error=str(exc))

    # Repository fallback
    repo = FinanceRepository()
    al = await repo.create_alert(
        user_id=user_id,
        description=body.name,
        alert_type=body.alert_type,
        threshold_usd=body.threshold_amount,
        status="active" if body.enabled else "paused",
    )
    return AlertResponse(
        id=al.id,
        name=al.description,
        alert_type=al.alert_type,
        threshold_amount=al.threshold_usd,
        category=body.category,
        institution=body.institution,
        enabled=(al.status == "active"),
        status="Active" if al.status == "active" else "Pause",
        last_triggered_at=None,
        created_at=al.created_at,
    )


@router.patch("/alerts/{alert_id}/status", response_model=dict[str, Any])
async def toggle_alert_status(
    alert_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Toggle alert status between Active and Pause."""
    user_id = str(current_user.id)
    factory = get_session_factory()
    if factory is not None:
        try:
            async with factory() as sess:
                res = await sess.execute(
                    select(SpendingAlert).where(
                        SpendingAlert.id == alert_id,
                        SpendingAlert.user_id == user_id,
                    )
                )
                alert = res.scalar_one_or_none()
                if alert:
                    alert.enabled = not alert.enabled
                    await sess.commit()
                    return {
                        "id": alert.id,
                        "enabled": alert.enabled,
                        "status": "Active" if alert.enabled else "Pause",
                    }
        except Exception as exc:
            log.warning("finance.alert.toggle_db_failed", error=str(exc))

    repo = FinanceRepository()
    toggled = await repo.toggle_alert_status(alert_id, user_id)
    if not toggled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    return {
        "id": toggled.id,
        "enabled": toggled.status == "active",
        "status": "Active" if toggled.status == "active" else "Pause",
    }


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a spending alert."""
    user_id = str(current_user.id)
    factory = get_session_factory()
    deleted = False

    if factory is not None:
        try:
            async with factory() as sess:
                del_alert_res = cast(
                    CursorResult[Any],
                    await sess.execute(
                        delete(SpendingAlert).where(
                            SpendingAlert.id == alert_id,
                            SpendingAlert.user_id == user_id,
                        )
                    ),
                )
                rowcount = getattr(del_alert_res, "rowcount", None) or 0
                if rowcount > 0:
                    deleted = True
                await sess.commit()
        except Exception as exc:
            log.warning("finance.alert.delete_db_failed", error=str(exc))

    if not deleted:
        repo = FinanceRepository()
        deleted = await repo.delete_alert(alert_id, user_id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    log.info("finance.alert.deleted", user_id=user_id, alert_id=alert_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
