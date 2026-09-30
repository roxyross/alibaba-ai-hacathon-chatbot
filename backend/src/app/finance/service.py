"""Personal Finance & Multi-Tenant Ledger Service.

Provides unified domain logic for connected financial accounts, multi-currency
balances (USD & PKR), transaction ledger records, spending summaries, and
Central Tool Registry integration with Action Center confirmation gating.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from app.finance.repository import FinanceRepository
from app.models.finance_account import FinanceAccount
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

logger = logging.getLogger(__name__)


class FinanceService:
    """Enterprise domain service for personal finance, accounts, and ledger tracking."""

    _instance: ClassVar[FinanceService | None] = None

    def __init__(self, repository: FinanceRepository | None = None) -> None:
        self.repo = repository or FinanceRepository()

    @classmethod
    def get_instance(cls, repository: FinanceRepository | None = None) -> FinanceService:
        """Get or initialize singleton instance of FinanceService."""
        if cls._instance is None:
            cls._instance = cls(repository=repository)
        return cls._instance

    # -------------------------------------------------------------------------
    # Core Domain Delegations
    # -------------------------------------------------------------------------

    async def list_accounts(self, user_id: str) -> list[dict[str, Any]]:
        """List all connected accounts owned by the user."""
        accounts = await self.repo.list_accounts(user_id=user_id)
        return [
            {
                "id": a.id,
                "institution": a.institution_name,
                "account_holder": a.account_holder,
                "type": a.account_type,
                "mask": a.account_number_masked[-4:] if len(a.account_number_masked) >= 4 else a.account_number_masked,
                "balance_usd": a.balance_usd,
                "balance_pkr": a.balance_pkr,
                "budget_usd": a.budget_limit_usd,
                "budget_pkr": a.budget_limit_pkr,
                "provider": a.provider,
                "status": a.status,
            }
            for a in accounts
        ]

    async def get_account(self, account_id: str, user_id: str) -> dict[str, Any] | None:
        """Get account details with recent transactions."""
        account = await self.repo.get_account(account_id=account_id, user_id=user_id)
        if not account:
            return None
        txs = await self.repo.list_transactions(user_id=user_id, account_id=account_id, limit=10)
        return {
            "id": account.id,
            "institution": account.institution_name,
            "account_holder": account.account_holder,
            "type": account.account_type,
            "mask": account.account_number_masked[-4:] if len(account.account_number_masked) >= 4 else account.account_number_masked,
            "balance_usd": account.balance_usd,
            "balance_pkr": account.balance_pkr,
            "budget_usd": account.budget_limit_usd,
            "budget_pkr": account.budget_limit_pkr,
            "provider": account.provider,
            "status": account.status,
            "recent_transactions": [
                {
                    "id": t.id,
                    "description": t.description,
                    "category": t.category,
                    "amount_usd": t.amount_usd,
                    "amount_pkr": t.amount_pkr,
                    "type": t.transaction_type,
                    "date": t.transaction_date.isoformat() if t.transaction_date else None,
                }
                for t in txs
            ],
        }

    async def create_account(
        self,
        user_id: str,
        account_holder: str,
        institution_name: str,
        account_type: str = "checking",
        account_number_full: str = "000012345678",
        account_number_masked: str = "••••5678",
        balance_usd: float = 0.0,
        balance_pkr: float = 0.0,
        budget_limit_usd: float = 1000.0,
        budget_limit_pkr: float = 300000.0,
        provider: str = "plaid",
    ) -> dict[str, Any]:
        """Create and persist a new financial account."""
        acc: FinanceAccount = await self.repo.create_account(
            user_id=user_id,
            account_holder=account_holder,
            institution_name=institution_name,
            account_type=account_type,
            account_number_full=account_number_full,
            account_number_masked=account_number_masked,
            balance_usd=balance_usd,
            balance_pkr=balance_pkr,
            budget_limit_usd=budget_limit_usd,
            budget_limit_pkr=budget_limit_pkr,
            provider=provider,
            status="active",
        )
        return {
            "id": acc.id,
            "institution": acc.institution_name,
            "account_holder": acc.account_holder,
            "type": acc.account_type,
            "mask": acc.account_number_masked[-4:],
            "balance_usd": acc.balance_usd,
            "balance_pkr": acc.balance_pkr,
            "provider": acc.provider,
        }

    async def delete_account(self, account_id: str, user_id: str) -> bool:
        """Disconnect/delete a financial account."""
        return await self.repo.delete_account(account_id=account_id, user_id=user_id)

    async def record_transaction(
        self,
        account_id: str,
        user_id: str,
        description: str,
        amount_usd: float,
        amount_pkr: float,
        category: str = "general",
        transaction_type: str = "debit",
        reason: str = "",
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Record a transaction and update account balance."""
        tx = await self.repo.create_transaction(
            user_id=user_id,
            account_id=account_id,
            description=description,
            reason=reason,
            category=category,
            amount_usd=amount_usd,
            amount_pkr=amount_pkr,
            transaction_type=transaction_type,
            metadata_json=metadata_json,
        )
        if not tx:
            return None

        # Update account balance accordingly
        multiplier = -1.0 if transaction_type == "debit" else 1.0
        await self.repo.update_balance(
            account_id=account_id,
            user_id=user_id,
            delta_usd=round(amount_usd * multiplier, 2),
            delta_pkr=round(amount_pkr * multiplier, 2),
        )

        return {
            "id": tx.id,
            "account_id": tx.account_id,
            "description": tx.description,
            "category": tx.category,
            "amount_usd": tx.amount_usd,
            "amount_pkr": tx.amount_pkr,
            "type": tx.transaction_type,
            "date": tx.transaction_date.isoformat() if tx.transaction_date else None,
        }

    async def list_transactions(
        self,
        user_id: str,
        account_id: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List financial transactions for the user."""
        txs = await self.repo.list_transactions(
            user_id=user_id,
            account_id=account_id,
            limit=limit,
        )
        if category:
            txs = [t for t in txs if (t.category or "").lower() == category.lower()]
        return [
            {
                "id": t.id,
                "account_id": t.account_id,
                "description": t.description,
                "category": t.category,
                "amount_usd": t.amount_usd,
                "amount_pkr": t.amount_pkr,
                "type": t.transaction_type,
                "is_pinned": t.is_pinned,
                "date": t.transaction_date.isoformat() if t.transaction_date else None,
            }
            for t in txs
        ]

    async def get_summary(self, user_id: str) -> dict[str, Any]:
        """Compute aggregated balance, accounts count, and monthly burn rate."""
        accounts = await self.list_accounts(user_id=user_id)
        txs = await self.list_transactions(user_id=user_id, limit=100)
        total_balance_usd = sum(a["balance_usd"] for a in accounts)
        total_balance_pkr = sum(a["balance_pkr"] for a in accounts)

        # Monthly debits
        monthly_spend_usd = sum(t["amount_usd"] for t in txs if t["type"] == "debit")
        monthly_spend_pkr = sum(t["amount_pkr"] for t in txs if t["type"] == "debit")

        return {
            "user_id": user_id,
            "total_accounts": len(accounts),
            "accounts_count": len(accounts),
            "total_balance_usd": round(total_balance_usd, 2),
            "total_net_worth_usd": round(total_balance_usd, 2),
            "total_balance_pkr": round(total_balance_pkr, 2),
            "total_net_worth_pkr": round(total_balance_pkr, 2),
            "monthly_spend_usd": round(monthly_spend_usd, 2),
            "monthly_spending_burn_rate_usd": round(monthly_spend_usd, 2),
            "monthly_spend_pkr": round(monthly_spend_pkr, 2),
            "monthly_spending_burn_rate_pkr": round(monthly_spend_pkr, 2),
            "accounts": accounts,
            "summary": (
                f"Total net worth: ${total_balance_usd:,.2f} USD (Rs. {total_balance_pkr:,.2f} PKR) "
                f"across {len(accounts)} connected accounts. Monthly spending: ${monthly_spend_usd:,.2f}."
            ),
        }

    # -------------------------------------------------------------------------
    # Central Tool Registry Registration
    # -------------------------------------------------------------------------

    def register_finance_tools(self) -> None:
        """Register personal finance and ledger tools into the Central ToolRegistry."""
        reg = ToolRegistry.get_instance()

        # 1. finance_list_accounts
        async def _tool_finance_list_accounts(user_id: str | None = None) -> dict[str, Any]:
            uid = user_id or "default"
            accounts = await self.list_accounts(user_id=uid)
            return {
                "user_id": uid,
                "total": len(accounts),
                "total_accounts": len(accounts),
                "accounts": accounts,
                "summary": f"Found {len(accounts)} connected bank and financial accounts.",
            }

        reg.register(
            AgentTool(
                id="finance_list_accounts",
                name="List Financial Accounts",
                description="List all connected bank accounts, checking/savings ledgers, and balances in USD and PKR.",
                source=ToolSource.SYSTEM,
                capabilities=["finance", "accounts", "bank", "balance"],
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                permissions=["finance:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_finance_list_accounts,
        )

        # 2. finance_get_account
        async def _tool_finance_get_account(
            account_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            account = await self.get_account(account_id=account_id, user_id=uid)
            if not account:
                return {"account_id": account_id, "found": False, "error": f"Account '{account_id}' not found."}
            return {"account_id": account_id, "found": True, "account": account}

        reg.register(
            AgentTool(
                id="finance_get_account",
                name="Get Financial Account Details",
                description="Retrieve full details, balances, and recent transaction history for a specific financial account.",
                source=ToolSource.SYSTEM,
                capabilities=["finance", "account", "details", "transactions"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string", "description": "Unique ID of the financial account"},
                    },
                    "required": ["account_id"],
                },
                permissions=["finance:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_finance_get_account,
        )

        # 3. finance_record_transaction
        async def _tool_finance_record_transaction(
            account_id: str,
            description: str,
            amount_usd: float,
            category: str = "general",
            transaction_type: str = "debit",
            amount_pkr: float | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            pkr = amount_pkr if amount_pkr is not None else round(amount_usd * 280.0, 2)
            tx = await self.record_transaction(
                account_id=account_id,
                user_id=uid,
                description=description,
                amount_usd=amount_usd,
                amount_pkr=pkr,
                category=category,
                transaction_type=transaction_type,
            )
            if not tx:
                return {"success": False, "error": f"Account '{account_id}' not found. Cannot record transaction."}
            return {
                "success": True,
                "transaction": tx,
                "summary": f"Recorded {transaction_type} of ${amount_usd:,.2f} for '{description}'.",
            }

        reg.register(
            AgentTool(
                id="finance_record_transaction",
                name="Record Financial Transaction",
                description="Log an expense, debit, or income credit to an account ledger with category tracking.",
                source=ToolSource.SYSTEM,
                capabilities=["finance", "transactions", "record", "expense"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string", "description": "Target account ID"},
                        "description": {"type": "string", "description": "Transaction description or merchant name"},
                        "amount_usd": {"type": "number", "description": "Amount in USD"},
                        "category": {"type": "string", "default": "general", "description": "Expense category (e.g. food, tech, transport, travel)"},
                        "transaction_type": {"type": "string", "enum": ["debit", "credit"], "default": "debit"},
                    },
                    "required": ["account_id", "description", "amount_usd"],
                },
                permissions=["finance:write"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
            ),
            _tool_finance_record_transaction,
        )

        # 4. finance_list_transactions
        async def _tool_finance_list_transactions(
            account_id: str | None = None,
            category: str | None = None,
            limit: int = 50,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            txs = await self.list_transactions(user_id=uid, account_id=account_id, category=category, limit=limit)
            return {
                "user_id": uid,
                "total": len(txs),
                "transactions": txs,
                "summary": f"Retrieved {len(txs)} transactions.",
            }

        reg.register(
            AgentTool(
                id="finance_list_transactions",
                name="List Financial Transactions",
                description="Retrieve transaction history and expense ledger with optional account and category filters.",
                source=ToolSource.SYSTEM,
                capabilities=["finance", "transactions", "ledger", "history"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string", "description": "Optional account filter"},
                        "category": {"type": "string", "description": "Optional expense category filter"},
                        "limit": {"type": "integer", "default": 50, "description": "Max transactions to return"},
                    },
                },
                permissions=["finance:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_finance_list_transactions,
        )

        # 5. finance_get_summary
        async def _tool_finance_get_summary(user_id: str | None = None) -> dict[str, Any]:
            uid = user_id or "default"
            return await self.get_summary(user_id=uid)

        reg.register(
            AgentTool(
                id="finance_get_summary",
                name="Get Financial Summary & Net Worth",
                description="Compute total net worth, dual-currency balances (USD & PKR), and monthly spending burn rate.",
                source=ToolSource.SYSTEM,
                capabilities=["finance", "summary", "net_worth", "burn_rate"],
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                permissions=["finance:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_finance_get_summary,
        )

        # 6. finance_delete_account (HIGH RISK - requires confirmation)
        async def _tool_finance_delete_account(
            account_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            deleted = await self.delete_account(account_id=account_id, user_id=uid)
            return {
                "account_id": account_id,
                "deleted": deleted,
                "status": "deleted" if deleted else "not_found",
                "message": f"Account '{account_id}' disconnected." if deleted else f"Account '{account_id}' not found.",
            }

        reg.register(
            AgentTool(
                id="finance_delete_account",
                name="Disconnect Financial Account",
                description="Disconnect and delete a financial account and associated transactions. Requires user confirmation.",
                source=ToolSource.SYSTEM,
                capabilities=["finance", "account", "delete", "destructive"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string", "description": "ID of account to disconnect"},
                    },
                    "required": ["account_id"],
                },
                permissions=["finance:write"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
            ),
            _tool_finance_delete_account,
        )
