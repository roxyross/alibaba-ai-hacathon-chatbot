"""Business service logic for Semantic Memory and Memory Curator (Phase 18).

Coordinates memory persistence, deduplication, relevance scoring, autonomous
clustering and pruning (Memory Curator Agent), and GDPR-compliant data export.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.memory.repository import MemoryRepository

log = structlog.get_logger()


class MemoryService:
    """Service orchestrating semantic memory operations and the autonomous curator."""

    def __init__(self, repository: MemoryRepository) -> None:
        self.repo = repository

    # ---------------------------------------------------------------------------
    # Store & Deduplication
    # ---------------------------------------------------------------------------

    async def store_memory(
        self,
        user_id: str,
        content: str,
        importance: str = "normal",
        source: str = "user:explicit",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Store a new long-term semantic memory with duplicate detection."""
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Memory content cannot be empty.")
        if len(clean_content) > 4000:
            clean_content = clean_content[:4000]

        clean_tags = [t.strip().lower() for t in (tags or []) if t.strip()]

        # Check existing active memories for near-duplicate content
        existing, _ = await self.repo.list_memories(
            user_id=user_id,
            include_soft_deleted=False,
            limit=100,
        )
        content_lower = clean_content.lower()
        for mem in existing:
            existing_content = mem.get("content", "").strip().lower()
            if existing_content == content_lower:
                # Exact match: update importance if higher, and update tags
                new_importance = importance
                if mem.get("importance") == "forever" or importance == "forever":
                    new_importance = "forever"
                elif mem.get("importance") == "high" or importance == "high":
                    new_importance = "high"

                merged_tags = list(set(mem.get("tags", []) + clean_tags))
                updated = await self.repo.update_memory(
                    user_id=user_id,
                    memory_id=mem["id"],
                    importance=new_importance,
                    tags=merged_tags,
                )
                if updated:
                    return updated
                return mem

        # Store fresh memory
        return await self.repo.store_memory(
            user_id=user_id,
            content=clean_content,
            importance=importance,
            source=source,
            tags=clean_tags,
        )

    # ---------------------------------------------------------------------------
    # Retrieval & Scoring
    # ---------------------------------------------------------------------------

    async def retrieve_memory(
        self,
        user_id: str,
        query: str | None = None,
        tags: list[str] | None = None,
        importance: str | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Retrieve relevant memories using lexical and tag similarity with importance weighting."""
        active_memories, _ = await self.repo.list_memories(
            user_id=user_id,
            include_soft_deleted=False,
            limit=200,
        )
        if not active_memories:
            return [], 0

        query_tokens = set(re.findall(r"\w+", query.lower())) if query else set()
        tag_filters = {t.lower() for t in (tags or [])}

        scored_items: list[tuple[float, dict[str, Any]]] = []

        for mem in active_memories:
            # Check explicit importance filter if requested
            if importance and mem.get("importance") != importance:
                continue

            mem_tags = {t.lower() for t in mem.get("tags", [])}
            # If tags filter provided, require at least one matching tag
            if tag_filters and not mem_tags.intersection(tag_filters):
                continue

            content_tokens = set(re.findall(r"\w+", mem.get("content", "").lower()))
            base_score = 0.5  # default baseline if no query

            if query_tokens:
                overlap = len(query_tokens.intersection(content_tokens))
                tag_overlap = len(query_tokens.intersection(mem_tags))
                token_jaccard = overlap / max(1, len(query_tokens.union(content_tokens)))
                base_score = (token_jaccard * 0.7) + (0.3 if tag_overlap > 0 else 0.0)
                if overlap == 0 and tag_overlap == 0:
                    base_score = 0.0

            # Importance weighting bonus
            imp = mem.get("importance", "normal")
            if imp == "forever":
                base_score += 0.25
            elif imp == "high":
                base_score += 0.15
            elif imp == "low":
                base_score -= 0.10

            final_score = max(0.0, min(1.0, base_score))
            if final_score >= min_score and (not query_tokens or final_score > 0.0):
                scored_items.append((final_score, mem))

        # Sort descending by score, then by created_at
        scored_items.sort(
            key=lambda x: (x[0], x[1].get("created_at") or ""),
            reverse=True,
        )

        top_slice = scored_items[:top_k]
        result_entries: list[dict[str, Any]] = []
        retrieved_ids: list[str] = []

        for score, m in top_slice:
            retrieved_ids.append(m["id"])
            result_entries.append({
                "entry_id": m["id"],
                "content": m["content"],
                "importance": m["importance"],
                "source": m["source"],
                "tags": m.get("tags", []),
                "score": round(score, 3),
                "stored_at": m.get("created_at"),
            })

        # Record usage access in background
        if retrieved_ids:
            await self.repo.record_retrievals(user_id=user_id, memory_ids=retrieved_ids)

        return result_entries, len(scored_items)

    # ---------------------------------------------------------------------------
    # Memory Curator Autonomous Agent Pass
    # ---------------------------------------------------------------------------

    async def run_curator_pass(
        self, user_id: str, policy_override: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute scheduled or on-demand memory curation: cluster, summarize, soft-delete, and hard-delete."""
        start_time = time.perf_counter()
        now = datetime.now(UTC)

        # 1. Resolve policy
        policy = await self.repo.get_policy(user_id)
        if policy_override:
            policy.update(policy_override)

        summarize_after_days = policy.get("summarize_after_days", 30)
        cluster_min_size = policy.get("cluster_min_size", 3)
        soft_delete_days = policy.get("soft_delete_never_retrieved_days", 180)
        hard_delete_days = policy.get("hard_delete_after_days", 30)

        soft_deleted_count = 0
        hard_deleted_count = 0
        summarized_count = 0
        errors_count = 0
        clusters_formed: list[dict[str, Any]] = []
        diff_lines: list[str] = []

        # 2. Fetch all memories (active and soft-deleted)
        all_memories, _ = await self.repo.list_memories(
            user_id=user_id,
            include_soft_deleted=True,
            limit=1000,
        )
        scanned_count = len(all_memories)

        # 3. Hard-delete expired soft-deletes
        for mem in all_memories:
            if mem.get("is_soft_deleted") and mem.get("soft_deleted_at"):
                try:
                    sd_time = datetime.fromisoformat(mem["soft_deleted_at"])
                    if (now - sd_time) >= timedelta(days=hard_delete_days):
                        await self.repo.delete_memory(
                            user_id=user_id, memory_id=mem["id"], permanent=True
                        )
                        hard_deleted_count += 1
                        diff_lines.append(f"Hard-deleted expired memory: {mem['id']}")
                except Exception as err:
                    errors_count += 1
                    log.warning("curator.hard_delete_failed", memory_id=mem["id"], error=str(err))

        # 4. Soft-delete stale never-retrieved memories (importance != 'forever')
        active_memories = [m for m in all_memories if not m.get("is_soft_deleted")]
        for mem in active_memories:
            if mem.get("importance") == "forever":
                continue  # 'forever' memories are permanently exempt

            try:
                created = datetime.fromisoformat(mem["created_at"])
                age = now - created
                if mem.get("retrieval_count", 0) == 0 and age >= timedelta(days=soft_delete_days):
                    await self.repo.delete_memory(
                        user_id=user_id, memory_id=mem["id"], permanent=False
                    )
                    soft_deleted_count += 1
                    diff_lines.append(f"Soft-deleted stale memory (age: {age.days}d): {mem['id']}")
            except Exception as err:
                errors_count += 1
                log.warning("curator.soft_delete_failed", memory_id=mem["id"], error=str(err))

        # 5. Cluster and summarize older active memories
        # Group active memories by primary tag or topic
        clusters: dict[str, list[dict[str, Any]]] = {}
        for mem in active_memories:
            if mem.get("importance") == "forever":
                continue
            if mem.get("cluster_id"):
                continue  # already summarized

            tags = mem.get("tags") or []
            if tags:
                primary_tag = tags[0].lower()
                clusters.setdefault(primary_tag, []).append(mem)

        for topic, cluster_mems in clusters.items():
            if len(cluster_mems) >= cluster_min_size:
                # Check if cluster entries are older than summarize threshold
                old_entries = []
                for m in cluster_mems:
                    try:
                        c_date = datetime.fromisoformat(m["created_at"])
                        if (now - c_date) >= timedelta(days=summarize_after_days):
                            old_entries.append(m)
                    except Exception:
                        pass

                if len(old_entries) >= cluster_min_size:
                    # Summarize cluster
                    source_ids = [m["id"] for m in old_entries]
                    summary_text = (
                        f"Consolidated summary for '{topic}': "
                        + "; ".join(m["content"] for m in old_entries[:5])
                    )
                    cluster_id = f"cluster_{topic}_{int(time.time())}"

                    # Store new summary entry
                    await self.repo.store_memory(
                        user_id=user_id,
                        content=summary_text,
                        importance="normal",
                        source="job:curator",
                        tags=[topic, "summarized"],
                        cluster_id=cluster_id,
                        source_entry_ids=source_ids,
                    )

                    # Soft-delete original entries
                    for m in old_entries:
                        await self.repo.update_memory(
                            user_id=user_id,
                            memory_id=m["id"],
                            is_soft_deleted=True,
                            soft_delete_reason=f"curator:summarized_into_{cluster_id}",
                        )

                    summarized_count += len(old_entries)
                    clusters_formed.append({
                        "cluster_id": cluster_id,
                        "topic": topic,
                        "entries_count": len(old_entries),
                    })
                    diff_lines.append(f"Summarized {len(old_entries)} memories into '{cluster_id}'")

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        diff_summary = (
            "\n".join(diff_lines)
            if diff_lines
            else f"Scanned {scanned_count} entries. Memory store is healthy and optimized; no pruning required."
        )

        report = await self.repo.record_curator_report(
            user_id=user_id,
            entries_scanned=scanned_count,
            summarized_count=summarized_count,
            clusters_formed=clusters_formed,
            soft_deleted_count=soft_deleted_count,
            hard_deleted_count=hard_deleted_count,
            errors_count=errors_count,
            duration_ms=duration_ms,
            status="completed" if errors_count == 0 else "completed_with_errors",
            diff_summary=diff_summary,
        )
        return report

    # ---------------------------------------------------------------------------
    # Natural Conversation Fact Extraction
    # ---------------------------------------------------------------------------

    async def extract_and_store_from_text(
        self, user_id: str, text: str, source: str = "agent:chat"
    ) -> list[dict[str, Any]]:
        """Extract explicit preference or fact patterns from chat text."""
        stored: list[dict[str, Any]] = []
        patterns = [
            (re.compile(r"\b(remember\s+(?:that\s+)?)(.+)", re.I), "forever", ["user_fact"]),
            (re.compile(r"\b(i\s+prefer\s+)(.+)", re.I), "high", ["preference"]),
            (re.compile(r"\b(my\s+name\s+is\s+)(.+)", re.I), "forever", ["identity"]),
            (re.compile(r"\b(i\s+live\s+in\s+)(.+)", re.I), "high", ["location"]),
            (re.compile(r"\b(always\s+use\s+)(.+)", re.I), "high", ["preference"]),
            (re.compile(r"\b(never\s+use\s+)(.+)", re.I), "high", ["constraint"]),
        ]

        for regex, imp, default_tags in patterns:
            match = regex.search(text)
            if match:
                fact = match.group(0).strip()
                # Clean up trailing punctuation
                fact = re.sub(r"[.!?]+$", "", fact)
                if len(fact) >= 5:
                    item = await self.store_memory(
                        user_id=user_id,
                        content=fact,
                        importance=imp,
                        source=source,
                        tags=default_tags,
                    )
                    stored.append(item)
        return stored

    # ---------------------------------------------------------------------------
    # Data Export & Right to Erasure
    # ---------------------------------------------------------------------------

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """Export all user memory records as a portable JSON archive."""
        all_memories, total = await self.repo.list_memories(
            user_id=user_id,
            include_soft_deleted=True,
            limit=10000,
        )
        stats = await self.repo.get_stats(user_id)

        return {
            "user_id": user_id,
            "exported_at": datetime.now(UTC).isoformat(),
            "total_memories": total,
            "telemetry": stats,
            "memories": all_memories,
            "note": "Complete user-scoped personal AI memory archive.",
        }

    async def purge_all(self, user_id: str) -> int:
        """Permanently erase all user memories."""
        return await self.repo.purge_all_memories(user_id)
