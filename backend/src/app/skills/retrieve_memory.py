"""retrieve_memory skill — search the user's long-term memory store."""

from app.skills.base import SkillExecutor
from app.skills.memory_store import get_memory_store
from app.skills.schemas import (
    Importance,
    MemoryEntry,
    RetrieveMemoryRequest,
    RetrieveMemoryResponse,
)


class RetrieveMemorySkill(SkillExecutor[RetrieveMemoryRequest, RetrieveMemoryResponse]):
    slug = "retrieve_memory"

    async def execute(self, input_data: RetrieveMemoryRequest) -> RetrieveMemoryResponse:
        store = get_memory_store()

        results = store.search(
            query=input_data.query,
            limit=input_data.limit,
            tags=input_data.tags if input_data.tags else None,
            user_id=input_data.user_id or "anonymous",
        )

        entries = [
            MemoryEntry(
                entry_id=entry.entry_id,
                content=entry.content,
                tags=entry.tags,
                importance=Importance(entry.importance.value),
                source=entry.source,
                stored_at=entry.stored_at,
                relevance_score=score,
            )
            for entry, score in results
        ]

        return RetrieveMemoryResponse(
            entries=entries,
            query=input_data.query,
        )


def get_executor() -> RetrieveMemorySkill:
    return RetrieveMemorySkill()
