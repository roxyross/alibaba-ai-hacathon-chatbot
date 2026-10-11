"""User Data Export and Account Deletion Services.

Implements Sections 9 and 10 of Trust and Reliability Layer.
Strict tenant isolation, explicit retention disclosures, cascading cleanup.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import MagicLinkToken, User
from app.chat_history.models import ChatMessage
from app.models.connector import ConnectorInstance
from app.models.custom_skill import CustomSkill
from app.models.document_vault import DocumentRecord
from app.models.generated_image import GeneratedImage
from app.models.mcp import MCPServerConfig
from app.models.media_job import MediaAsset
from app.models.project import Project, ProjectTask
from app.models.scheduled_job import ScheduledJob
from app.models.semantic_memory import SemanticMemory
from app.models.token_usage import TokenUsageLog
from app.models.trust import DataExportJob, PersonalizationProposal, RecoveryJob, TrustEvent
from app.models.user_preference import UserPreference
from app.session.models import ChatSession

log = structlog.get_logger()


class DataControlService:
    """Handles secure user data export and compliant data/account deletion."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_export_job(self, user_id: str) -> DataExportJob:
        """Create a job exporting all personal data for the user."""
        job = DataExportJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status="processing",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        self.db.add(job)
        await self.db.commit()

        # Collect user data across domains
        try:
            # 1. Sessions & Messages
            sess_res = await self.db.execute(
                select(ChatSession).where(ChatSession.user_id == user_id)
            )
            sessions = [
                {
                    "id": s.id,
                    "title": s.title,
                    "session_type": getattr(s, "session_type", "chat"),
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in sess_res.scalars().all()
            ]

            session_ids = [s["id"] for s in sessions]
            messages = []
            if session_ids:
                msg_res = await self.db.execute(
                    select(ChatMessage).where(ChatMessage.session_id.in_(session_ids))
                )
                messages = [
                    {
                        "id": m.id,
                        "session_id": m.session_id,
                        "sender": m.sender,
                        "content": m.content,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in msg_res.scalars().all()
                ]

            # 2. Semantic Memories
            mem_res = await self.db.execute(
                select(SemanticMemory).where(SemanticMemory.user_id == user_id)
            )
            memories = [
                {
                    "id": m.id,
                    "content": m.content,
                    "category": m.category,
                    "importance": m.importance,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in mem_res.scalars().all()
            ]

            # 3. Preferences & Personalization
            pref_res = await self.db.execute(
                select(UserPreference).where(UserPreference.user_id == user_id)
            )
            pref = pref_res.scalar_one_or_none()
            preferences = {
                "theme": pref.theme if pref else "dark",
                "language": pref.language if pref else "en",
                "custom_instructions": pref.custom_instructions if pref else None,
            }

            # 4. Knowledge Vault Documents
            doc_res = await self.db.execute(
                select(DocumentRecord).where(DocumentRecord.user_id == user_id)
            )
            documents = [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "title": getattr(d, "title", d.filename),
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in doc_res.scalars().all()
            ]

            # 5. Projects & Tasks
            proj_res = await self.db.execute(
                select(Project).where(Project.user_id == user_id)
            )
            projects = [
                {
                    "id": p.id,
                    "title": p.title,
                    "description": p.description,
                    "status": p.status,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in proj_res.scalars().all()
            ]

            # 6. Scheduled Jobs & Automations
            jobs_res = await self.db.execute(
                select(ScheduledJob).where(ScheduledJob.user_id == user_id)
            )
            scheduled_jobs = [
                {
                    "id": j.id,
                    "name": j.name,
                    "schedule_cron": j.schedule_cron,
                    "action_type": j.action_type,
                    "is_active": j.is_active,
                }
                for j in jobs_res.scalars().all()
            ]

            # 7. Generated Media Assets
            img_res = await self.db.execute(
                select(GeneratedImage).where(GeneratedImage.user_id == user_id)
            )
            media_items = [
                {
                    "id": img.id,
                    "prompt": img.prompt,
                    "image_url": img.image_url,
                    "created_at": img.created_at.isoformat() if img.created_at else None,
                }
                for img in img_res.scalars().all()
            ]

            # 8. Connected Accounts & MCP metadata
            conn_res = await self.db.execute(
                select(ConnectorInstance).where(ConnectorInstance.user_id == user_id)
            )
            connectors = [
                {
                    "id": c.id,
                    "connector_type": c.connector_type,
                    "name": c.name,
                    "status": c.status,
                }
                for c in conn_res.scalars().all()
            ]

            # 9. Trust Events & Audit Trail
            trust_res = await self.db.execute(
                select(TrustEvent).where(TrustEvent.user_id == user_id).limit(200)
            )
            trust_events = [t.to_dict() for t in trust_res.scalars().all()]

            export_data = {
                "version": "2.0",
                "exported_at": datetime.now(UTC).isoformat(),
                "user_id": user_id,
                "sessions": sessions,
                "messages": messages,
                "memories": memories,
                "documents": documents,
                "projects": projects,
                "scheduled_jobs": scheduled_jobs,
                "generated_media": media_items,
                "connectors": connectors,
                "preferences": preferences,
                "trust_events": trust_events,
            }

            job.status = "completed"
            job.export_payload_json = json.dumps(export_data)
            job.completed_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(job)

            log.info("user_export_completed", user_id=user_id, job_id=job.id)
            return job

        except Exception as e:
            log.exception("export_job_failed", user_id=user_id, error=str(e))
            job.status = "failed"
            await self.db.commit()
            return job

    async def get_export_job(self, job_id: str, user_id: str) -> dict[str, Any] | None:
        """Retrieve export job if owned by user."""
        stmt = select(DataExportJob).where(
            DataExportJob.id == job_id, DataExportJob.user_id == user_id
        )
        res = await self.db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            return None

        payload = None
        if job.export_payload_json:
            try:
                payload = json.loads(job.export_payload_json)
            except Exception:
                payload = None

        return {
            "id": job.id,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "expires_at": job.expires_at.isoformat() if job.expires_at else None,
            "data": payload,
        }

    async def delete_user_data(self, user_id: str) -> dict[str, Any]:
        """Cascade delete user chat, memory, and personal artifacts while preserving legal audit logs."""
        # 1. Chat sessions and messages
        sess_stmt = select(ChatSession.id).where(ChatSession.user_id == user_id)
        sess_res = await self.db.execute(sess_stmt)
        s_ids = list(sess_res.scalars().all())

        deleted_counts = {}
        if s_ids:
            msg_del = await self.db.execute(
                delete(ChatMessage).where(ChatMessage.session_id.in_(s_ids))
            )
            deleted_counts["messages"] = msg_del.rowcount or 0

            sess_del = await self.db.execute(
                delete(ChatSession).where(ChatSession.id.in_(s_ids))
            )
            deleted_counts["sessions"] = sess_del.rowcount or 0

        # 2. Semantic memories
        mem_del = await self.db.execute(
            delete(SemanticMemory).where(SemanticMemory.user_id == user_id)
        )
        deleted_counts["memories"] = mem_del.rowcount or 0

        # 3. Personalization proposals
        pers_del = await self.db.execute(
            delete(PersonalizationProposal).where(PersonalizationProposal.user_id == user_id)
        )
        deleted_counts["personalization_proposals"] = pers_del.rowcount or 0

        # 4. Recovery jobs
        rec_del = await self.db.execute(
            delete(RecoveryJob).where(RecoveryJob.user_id == user_id)
        )
        deleted_counts["recovery_jobs"] = rec_del.rowcount or 0

        # 5. Documents
        doc_del = await self.db.execute(
            delete(DocumentRecord).where(DocumentRecord.user_id == user_id)
        )
        deleted_counts["documents"] = doc_del.rowcount or 0

        # 6. Projects & Project Tasks
        p_stmt = select(Project.id).where(Project.user_id == user_id)
        p_res = await self.db.execute(p_stmt)
        p_ids = list(p_res.scalars().all())
        if p_ids:
            pt_del = await self.db.execute(
                delete(ProjectTask).where(ProjectTask.project_id.in_(p_ids))
            )
            deleted_counts["project_tasks"] = pt_del.rowcount or 0
        proj_del = await self.db.execute(
            delete(Project).where(Project.user_id == user_id)
        )
        deleted_counts["projects"] = proj_del.rowcount or 0

        # 7. Scheduled Jobs & Automations
        job_del = await self.db.execute(
            delete(ScheduledJob).where(ScheduledJob.user_id == user_id)
        )
        deleted_counts["scheduled_jobs"] = job_del.rowcount or 0

        # 8. Generated Media
        img_del = await self.db.execute(
            delete(GeneratedImage).where(GeneratedImage.user_id == user_id)
        )
        deleted_counts["generated_images"] = img_del.rowcount or 0

        # 9. Custom Skills
        skill_del = await self.db.execute(
            delete(CustomSkill).where(CustomSkill.user_id == user_id)
        )
        deleted_counts["custom_skills"] = skill_del.rowcount or 0

        await self.db.commit()

        log.info("user_data_deleted", user_id=user_id, counts=deleted_counts)
        return {
            "success": True,
            "deleted": deleted_counts,
            "retention_notice": "Statutory security and billing logs are retained in accordance with legal requirements.",
        }

    async def delete_account(self, user_id: str, confirmation: str) -> dict[str, Any]:
        """Permanent account termination with explicit verification phrase."""
        if confirmation != "DELETE MY ACCOUNT":
            return {
                "success": False,
                "reason": "Confirmation phrase mismatch. Please enter 'DELETE MY ACCOUNT'.",
            }

        # Clear personal data first
        await self.delete_user_data(user_id)

        # Clear magic links and user record
        await self.db.execute(
            delete(MagicLinkToken).where(MagicLinkToken.user_id == user_id)
        )
        user_del = await self.db.execute(delete(User).where(User.id == user_id))
        await self.db.commit()

        log.info("user_account_deleted", user_id=user_id)
        return {
            "success": True,
            "message": "Account and associated data have been permanently removed.",
        }
