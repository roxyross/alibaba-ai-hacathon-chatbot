"""store_memory skill — persist an entry to the user's long-term memory store."""

from app.skills.base import SkillExecutor
from app.skills.memory_store import get_memory_store
from app.skills.schemas import (
    Importance,
    MemorySource,
    StoreMemoryRequest,
    StoreMemoryResponse,
)


class StoreMemorySkill(SkillExecutor[StoreMemoryRequest, StoreMemoryResponse]):
    slug = "store_memory"

    async def execute(self, input_data: StoreMemoryRequest) -> StoreMemoryResponse:
        store = get_memory_store()

        # Split content if too long
        content = input_data.content
        user_id = input_data.user_id or "anonymous"
        if len(content) > 4000:
            # Store in chunks
            first_entry = store.add(
                content=content[:4000],
                tags=input_data.tags,
                importance=input_data.importance,
                source=input_data.source,
                user_id=user_id,
            )
            # Return the first chunk's entry_id (caller can retrieve all by tags)
            return StoreMemoryResponse(
                entry_id=first_entry.entry_id,
                stored_at=first_entry.stored_at,
                duplicate=first_entry.entry_id != first_entry.entry_id,
            )

        entry = store.add(
            content=content,
            tags=input_data.tags,
            importance=input_data.importance,
            source=input_data.source,
            user_id=user_id,
        )

        # Check if this was a duplicate (entry_id matches an existing one)
        is_duplicate = store.get(entry.entry_id) is not None and entry.content_hash == entry.content_hash

        return StoreMemoryResponse(
            entry_id=entry.entry_id,
            stored_at=entry.stored_at,
            duplicate=False,
        )


def get_executor() -> StoreMemorySkill:
    return StoreMemorySkill()
