"""Controlled Personalization Engine.

Implements Section 17 of Trust and Reliability Layer.
User control, explicit approval, transparent rationales, reset capability.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trust import PersonalizationProposal
from app.models.user_preference import UserPreference

log = structlog.get_logger()


class PersonalizationService:
    """Manages explicit user-approved preferences and learned habits."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def propose_preference(
        self,
        user_id: str,
        category: str,
        key: str,
        proposed_value: str,
        rationale: str,
    ) -> PersonalizationProposal:
        """Create a transparent preference proposal that awaits explicit user consent."""
        # Check if identical proposal already pending
        stmt = select(PersonalizationProposal).where(
            PersonalizationProposal.user_id == user_id,
            PersonalizationProposal.key == key,
            PersonalizationProposal.status == "pending",
        )
        res = await self.db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            existing.proposed_value = proposed_value
            existing.rationale = rationale
            await self.db.commit()
            return existing

        proposal = PersonalizationProposal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            category=category,
            key=key,
            proposed_value=proposed_value,
            rationale=rationale,
            status="pending",
        )
        self.db.add(proposal)
        await self.db.commit()
        await self.db.refresh(proposal)

        log.info(
            "personalization_proposed",
            user_id=user_id,
            key=key,
            category=category,
        )
        return proposal

    async def list_proposals(
        self, user_id: str, status: str | None = None
    ) -> list[PersonalizationProposal]:
        stmt = select(PersonalizationProposal).where(PersonalizationProposal.user_id == user_id)
        if status:
            stmt = stmt.where(PersonalizationProposal.status == status)
        stmt = stmt.order_by(desc(PersonalizationProposal.created_at))
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def resolve_proposal(
        self, proposal_id: str, user_id: str, approve: bool
    ) -> dict[str, Any]:
        """User approves or rejects a proposed preference."""
        stmt = select(PersonalizationProposal).where(
            PersonalizationProposal.id == proposal_id,
            PersonalizationProposal.user_id == user_id,
        )
        res = await self.db.execute(stmt)
        proposal = res.scalar_one_or_none()
        if not proposal:
            return {"success": False, "reason": "Proposal not found."}

        proposal.resolved_at = datetime.now(UTC)
        if approve:
            proposal.status = "approved"
            # Apply to UserPreference
            pref_stmt = select(UserPreference).where(UserPreference.user_id == user_id)
            pref_res = await self.db.execute(pref_stmt)
            pref = pref_res.scalar_one_or_none()
            if not pref:
                pref = UserPreference(user_id=user_id)
                self.db.add(pref)

            if proposal.key == "theme":
                pref.theme = proposal.proposed_value
            elif proposal.key == "custom_persona":
                pref.custom_persona = proposal.proposed_value
            else:
                extra = dict(pref.extra_settings or {})
                extra[proposal.key] = proposal.proposed_value
                pref.extra_settings = extra

            await self.db.commit()
            return {
                "success": True,
                "status": "approved",
                "message": f"Preference '{proposal.key}' has been updated to '{proposal.proposed_value}'.",
            }
        else:
            proposal.status = "rejected"
            await self.db.commit()
            return {
                "success": True,
                "status": "rejected",
                "message": f"Preference proposal for '{proposal.key}' was declined.",
            }

    async def reset_personalization(self, user_id: str) -> dict[str, Any]:
        """Clear all learned personalization and reset to defaults."""
        await self.db.execute(
            delete(PersonalizationProposal).where(PersonalizationProposal.user_id == user_id)
        )
        pref_stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        pref_res = await self.db.execute(pref_stmt)
        pref = pref_res.scalar_one_or_none()
        if pref:
            pref.theme = "dark"
            pref.custom_persona = ""
            pref.extra_settings = {}
        await self.db.commit()

        log.info("personalization_reset", user_id=user_id)
        return {
            "success": True,
            "message": "Personalization preferences have been reset to factory defaults.",
        }
