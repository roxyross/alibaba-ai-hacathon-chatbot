"""Usage API router — token analytics, 30-day chart timeline, credits and cost."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(prefix="/usage", tags=["usage"])


# Per-user token logs tracker for multi-tenant isolation and user-specific billing
_USER_TOKEN_LOGS: dict[str, list[dict[str, Any]]] = {}


def record_user_tokens(
    user_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float = 0.0,
    provider_id: str = "gemini",
    model_id: str = "gemini-2.0-flash",
) -> None:
    """Record token usage attributed to a specific user."""
    if user_id not in _USER_TOKEN_LOGS:
        _USER_TOKEN_LOGS[user_id] = []
    _USER_TOKEN_LOGS[user_id].insert(0, {
        "id": f"tok_{datetime.now(UTC).timestamp()}",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "provider_id": provider_id,
        "model_id": model_id,
        "timestamp": datetime.now(UTC).isoformat(),
    })


@router.get("/stats")
async def get_usage_stats(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return remaining credits, monthly consumption, estimated cost, and 30-day chart points for authenticated user."""
    user_id = str(user.id)
    now = datetime.now(UTC)
    logs: list[dict[str, Any]] = _USER_TOKEN_LOGS.get(user_id, [])

    # Calculate actual usage metrics
    prompt_tokens = sum(log.get("input_tokens", 0) for log in logs)
    completion_tokens = sum(log.get("output_tokens", 0) for log in logs)
    total_tokens = prompt_tokens + completion_tokens
    total_cost_usd = sum(log.get("cost_usd", 0.0) for log in logs)
    total_cost_pkr = round(total_cost_usd * 300.0, 2)
    credits_used = round(total_tokens / 1000.0, 2)
    starting_credits = 100.0

    try:
        from app.billing.repository import BillingRepository
        repo = BillingRepository()
        wallet = await repo.get_credit_wallet(user_id)
        if wallet and "remaining_credits" in wallet:
            starting_credits = wallet["remaining_credits"]
    except Exception:
        pass

    remaining_credits = max(0.0, round(starting_credits - credits_used, 2))

    # Construct 30-day timeline
    timeline: list[dict[str, Any]] = []
    base_date = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Bin logs by date if any exist
    daily_tokens: dict[str, int] = {}
    for log_item in logs:
        ts_str = log_item.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                date_key = dt.strftime("%b %d")
                daily_tokens[date_key] = daily_tokens.get(date_key, 0) + (
                    log_item.get("input_tokens", 0) + log_item.get("output_tokens", 0)
                )
            except Exception:
                pass

    for i in range(30):
        day = base_date + timedelta(days=i)
        date_str = day.strftime("%b %d")
        tokens_for_day = daily_tokens.get(date_str, 0)
        timeline.append({
            "date": date_str,
            "tokens": tokens_for_day,
            "cost_usd": round(tokens_for_day * 0.000004, 3),
        })

    # Format recent activity rows
    recent_activity: list[dict[str, Any]] = []
    for log_item in logs[:10]:
        t_tokens = log_item.get("input_tokens", 0) + log_item.get("output_tokens", 0)
        c_usd = log_item.get("cost_usd", 0.0)
        recent_activity.append({
            "id": log_item.get("id", log_item.get("request_id", "act")),
            "feature": f"AI Inference ({log_item.get('provider_id', 'gateway')})",
            "model": log_item.get("model_id", "default"),
            "tokens": t_tokens,
            "cost_usd": round(c_usd, 4),
            "cost_pkr": round(c_usd * 300.0, 2),
            "time": log_item.get("timestamp") or "Recently",
        })

    return {
        "total_tokens": total_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "remaining_credits": remaining_credits,
        "used_this_month": credits_used,
        "estimated_cost_usd": round(total_cost_usd, 3),
        "estimated_cost_pkr": total_cost_pkr,
        "timeline": timeline,
        "daily_timeline": timeline,
        "recent_activity": recent_activity,
    }
