"""In-memory + JSON-persisted memory store for store_memory / retrieve_memory."""

from __future__ import annotations

import json
import math
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from app.skills.schemas import Importance, MemorySource


class MemoryEntryModel(BaseModel):
    entry_id: str
    content: str
    content_hash: str
    tags: list[str]
    importance: Importance
    source: MemorySource | None
    stored_at: datetime
    user_id: str
    embedding: list[float] | None = None  # future: real embeddings

    @staticmethod
    def _simple_hash(content: str) -> str:
        """Fast deterministic hash for near-duplicate detection."""
        import hashlib
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @staticmethod
    def _simulate_embedding(content: str, dims: int = 128) -> list[float]:
        """Generate a pseudo-embedding from content for similarity scoring.

        Uses a deterministic hash so the same content always gets the same vector.
        Replace with a real embedding model (e.g., OpenAI embeddings) in production.
        """
        import hashlib
        h = hashlib.sha256(content.encode()).digest()
        # Normalise hash into dims-dimensional unit-ish vector
        vals = []
        for i in range(dims):
            # Use two consecutive bytes to produce a float in [-1, 1]
            b0 = h[(2 * i) % len(h)]
            b1 = h[(2 * i + 1) % len(h)]
            v = (b0 * 256 + b1) / 32768.0 - 1.0
            vals.append(v)
        # L2-normalise
        norm = math.sqrt(sum(x * x for x in vals))
        return [x / norm for x in vals] if norm > 0 else vals


class MemoryStore:
    """In-memory memory store with optional JSON persistence.

    File persistence path is controlled by MEMORY_STORE_PATH env var,
    defaulting to {project_root}/data/memory_store.json.

    All entries are partitioned by user_id for per-user data isolation.
    """

    def __init__(self) -> None:
        # user_id -> entry_id -> MemoryEntryModel
        self._entries: dict[str, dict[str, MemoryEntryModel]] = {}
        self._path = self._resolve_path()

    def _resolve_path(self) -> Path | None:
        raw = os.environ.get("MEMORY_STORE_PATH", "").strip()
        if not raw:
            # Default: {repo_root}/data/memory_store.json
            repo = Path(__file__).resolve().parents[3] / "data" / "memory_store.json"
            repo.parent.mkdir(parents=True, exist_ok=True)
            return repo
        return Path(raw)

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for d in raw:
                d["importance"] = Importance(d["importance"])
                if d.get("source"):
                    d["source"] = MemorySource(d["source"])
                if d.get("stored_at"):
                    d["stored_at"] = datetime.fromisoformat(d["stored_at"])
                entry = MemoryEntryModel(**d)
                user_id = d.get("user_id", "default")
                if user_id not in self._entries:
                    self._entries[user_id] = {}
                self._entries[user_id][entry.entry_id] = entry
        except Exception:
            pass  # Corrupt file → start fresh

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for partition in self._entries.values():
                for e in partition.values():
                    d = e.model_dump()
                    d["stored_at"] = e.stored_at.isoformat()
                    data.append(d)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # Non-fatal; in-memory still works

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def add(
        self,
        content: str,
        tags: list[str],
        importance: Importance,
        source: MemorySource | None,
        user_id: str,
    ) -> MemoryEntryModel:
        self._load()
        content_hash = MemoryEntryModel._simple_hash(content)
        now = datetime.now(timezone.utc)

        # Ensure user partition exists
        if user_id not in self._entries:
            self._entries[user_id] = {}

        # Check for near-duplicate within user partition
        user_entries = self._entries[user_id]
        for e in user_entries.values():
            if e.content_hash == content_hash and e.content == content:
                return e  # return existing — caller handles duplicate

        entry_id = str(uuid.uuid4())
        entry = MemoryEntryModel(
            entry_id=entry_id,
            content=content,
            content_hash=content_hash,
            tags=tags,
            importance=importance,
            source=source,
            stored_at=now,
            user_id=user_id,
            embedding=MemoryEntryModel._simulate_embedding(content),
        )
        self._entries[user_id][entry_id] = entry
        self._save()
        return entry

    def search(
        self,
        query: str,
        limit: int = 5,
        tags: list[str] = None,
        user_id: str | None = None,
    ) -> list[tuple[MemoryEntryModel, float]]:
        """Return entries sorted by cosine similarity to query, filtered by tags and user."""
        self._load()
        query_emb = MemoryEntryModel._simulate_embedding(query)
        results: list[tuple[MemoryEntryModel, float]] = []

        if user_id:
            user_entries = [self._entries.get(user_id, {})]
        else:
            # Fallback: search all users (backwards compat for admin reads)
            user_entries = list(self._entries.values())

        for partition in user_entries:
            for entry in partition.values():
                if tags and not any(t in entry.tags for t in tags):
                    continue
                if entry.embedding is None:
                    continue
                score = self._cosine(query_emb, entry.embedding)
                results.append((entry, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get(self, entry_id: str, user_id: str | None = None) -> MemoryEntryModel | None:
        self._load()
        if user_id:
            return self._entries.get(user_id, {}).get(entry_id)
        # Fallback: search all partitions
        for partition in self._entries.values():
            if entry_id in partition:
                return partition[entry_id]
        return None

    def list_all(self, limit: int = 100, user_id: str | None = None) -> list[MemoryEntryModel]:
        self._load()
        if user_id:
            entries = list(self._entries.get(user_id, {}).values())
        else:
            entries = [e for partition in self._entries.values() for e in partition.values()]
        return sorted(
            entries,
            key=lambda e: e.stored_at,
            reverse=True,
        )[:limit]

    def delete(self, entry_id: str, user_id: str | None = None) -> bool:
        self._load()
        if user_id:
            if entry_id in self._entries.get(user_id, {}):
                del self._entries[user_id][entry_id]
                self._save()
                return True
            return False
        # Fallback: try all partitions
        for partition in self._entries.values():
            if entry_id in partition:
                del partition[entry_id]
                self._save()
                return True
        return False

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        return max(0.0, dot)  # Non-negative


# Singleton store instance
_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
