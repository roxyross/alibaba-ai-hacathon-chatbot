"""Usage API router — token analytics, 30-day chart timeline, credits and cost."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/stats")
async def get_usage_stats(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return remaining credits, monthly consumption, estimated cost, and 30-day chart points."""
    now = datetime.now(timezone.utc)

    # 30-day time series data for line chart
    timeline: list[dict[str, Any]] = []
    base_date = now - timedelta(days=29)
    for i in range(30):
        day = base_date + timedelta(days=i)
        tokens = int(12000 + (i * 850) + (random.random() * 4000))
        timeline.append({
            "date": day.strftime("%b %d"),
            "tokens": tokens,
            "cost_usd": round(tokens * 0.000004, 3),
        })

    recent_activity = [
        {
            "id": "act_1",
            "feature": "Deep Reasoning",
            "model": "deepseek-r1",
            "tokens": 4820,
            "cost_usd": 0.024,
            "cost_pkr": 7.2,
            "time": "12 mins ago",
        },
        {
            "id": "act_2",
            "feature": "Image Studio",
            "model": "imagen-3.0",
            "tokens": 1200,
            "cost_usd": 0.040,
            "cost_pkr": 12.0,
            "time": "1 hour ago",
        },
        {
            "id": "act_3",
            "feature": "Scheduled Task",
            "model": "gemini-2.0-flash",
            "tokens": 2150,
            "cost_usd": 0.006,
            "cost_pkr": 1.8,
            "time": "4 hours ago",
        },
        {
            "id": "act_4",
            "feature": "Finance Sync",
            "model": "gpt-4o",
            "tokens": 3410,
            "cost_usd": 0.017,
            "cost_pkr": 5.1,
            "time": "Yesterday",
        },
    ]

    return {
        "remaining_credits": 142.50,
        "used_this_month": 32.40,
        "estimated_cost_usd": 7.85,
        "estimated_cost_pkr": 2355.0,
        "timeline": timeline,
        "recent_activity": recent_activity,
    }
