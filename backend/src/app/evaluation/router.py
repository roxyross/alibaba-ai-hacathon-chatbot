"""AI Reliability Evaluation API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.evaluation.dataset import EVALUATION_DATASET
from app.evaluation.service import EvaluationRunner

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/dataset")
async def get_dataset() -> dict[str, Any]:
    """Retrieve full test dataset for offline inspection or CI verification."""
    return {
        "total_cases": len(EVALUATION_DATASET),
        "cases": EVALUATION_DATASET,
    }


@router.post("/run")
async def run_evaluation(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger automated continuous evaluation run."""
    runner = EvaluationRunner(db)
    return await runner.run_evaluation()


@router.get("/runs")
async def get_previous_runs(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Retrieve history of previous evaluation runs and pass rates."""
    runner = EvaluationRunner(db)
    return await runner.get_latest_runs()
