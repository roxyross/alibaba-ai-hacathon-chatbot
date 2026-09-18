"""Dual-mode persistence repository for Code Snippets and Executions (Phase 17).

Supports async PostgreSQL ORM with thread-safe in-memory fallback stores
for deterministic testing and offline local execution.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_snippet import CodeExecution, CodeSnippet

log = structlog.get_logger()

# In-memory stores for testing / offline execution
_MEM_LOCK = threading.Lock()
_MEM_SNIPPETS: dict[str, dict[str, Any]] = {}
_MEM_EXECUTIONS: dict[str, dict[str, Any]] = {}


def clear_in_memory_stores() -> None:
    """Clear in-memory stores between test runs."""
    with _MEM_LOCK:
        _MEM_SNIPPETS.clear()
        _MEM_EXECUTIONS.clear()


class CodeRepository:
    """Repository handling code snippets, favorites, and execution runs."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self._use_db = session is not None and bool(os.environ.get("DATABASE_URL"))

    # ---------------------------------------------------------------------------
    # Code Snippets
    # ---------------------------------------------------------------------------

    async def list_snippets(
        self,
        user_id: str,
        language: str | None = None,
        is_favorite: bool | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List snippets for user with optional language, favorite, and search filters."""
        if self._use_db and self.session:
            query = select(CodeSnippet).where(CodeSnippet.user_id == user_id)
            if language:
                query = query.where(CodeSnippet.language.ilike(language))
            if is_favorite is not None:
                query = query.where(CodeSnippet.is_favorite == is_favorite)
            if search:
                pattern = f"%{search}%"
                query = query.where(
                    CodeSnippet.title.ilike(pattern)
                    | CodeSnippet.description.ilike(pattern)
                    | CodeSnippet.tags.ilike(pattern)
                    | CodeSnippet.code.ilike(pattern)
                )

            count_query = select(func.count()).select_from(query.subquery())
            total_res = await self.session.execute(count_query)
            total = total_res.scalar() or 0

            query = query.order_by(desc(CodeSnippet.is_favorite), desc(CodeSnippet.created_at)).limit(limit).offset(offset)
            res = await self.session.execute(query)
            snippets = [s.to_dict() for s in res.scalars().all()]
            return snippets, total

        with _MEM_LOCK:
            matched: list[dict[str, Any]] = []
            for item in _MEM_SNIPPETS.values():
                if item["user_id"] != user_id:
                    continue
                if language and item.get("language", "").lower() != language.lower():
                    continue
                if is_favorite is not None and item.get("is_favorite") != is_favorite:
                    continue
                if search:
                    s_lower = search.lower()
                    in_title = s_lower in item.get("title", "").lower()
                    in_desc = s_lower in (item.get("description") or "").lower()
                    in_code = s_lower in item.get("code", "").lower()
                    in_tags = any(s_lower in t.lower() for t in item.get("tags", []))
                    if not (in_title or in_desc or in_code or in_tags):
                        continue
                matched.append(dict(item))

            # Sort by favorite desc, then created_at desc
            matched.sort(
                key=lambda x: (x.get("is_favorite", False), x.get("created_at") or ""),
                reverse=True,
            )
            total = len(matched)
            return matched[offset : offset + limit], total

    async def get_snippet(self, user_id: str, snippet_id: str) -> dict[str, Any] | None:
        """Get single snippet by ID strictly guarded by user_id."""
        if self._use_db and self.session:
            query = select(CodeSnippet).where(
                CodeSnippet.id == snippet_id,
                CodeSnippet.user_id == user_id,
            )
            res = await self.session.execute(query)
            snip = res.scalar_one_or_none()
            return snip.to_dict() if snip else None

        with _MEM_LOCK:
            snip_dict = _MEM_SNIPPETS.get(snippet_id)
            if snip_dict and snip_dict["user_id"] == user_id:
                return dict(snip_dict)
            return None

    async def create_snippet(
        self,
        user_id: str,
        title: str,
        language: str,
        code: str,
        description: str | None = None,
        tags: list[str] | None = None,
        is_favorite: bool = False,
    ) -> dict[str, Any]:
        """Create new snippet record."""
        tag_list = tags or []
        tag_str = ",".join(tag_list) if tag_list else None
        now = datetime.now(UTC)

        if self._use_db and self.session:
            snip = CodeSnippet(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=title,
                language=language.lower(),
                code=code,
                description=description,
                tags=tag_str,
                is_favorite=is_favorite,
                created_at=now,
                updated_at=now,
            )
            self.session.add(snip)
            await self.session.commit()
            await self.session.refresh(snip)
            return snip.to_dict()

        snippet_id = str(uuid.uuid4())
        data: dict[str, Any] = {
            "id": snippet_id,
            "user_id": user_id,
            "title": title,
            "language": language.lower(),
            "code": code,
            "description": description,
            "tags": tag_list,
            "is_favorite": is_favorite,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        with _MEM_LOCK:
            _MEM_SNIPPETS[snippet_id] = data
        return dict(data)

    async def update_snippet(
        self,
        user_id: str,
        snippet_id: str,
        title: str | None = None,
        language: str | None = None,
        code: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        is_favorite: bool | None = None,
    ) -> dict[str, Any] | None:
        """Update existing snippet fields with strict user_id check."""
        now = datetime.now(UTC)

        if self._use_db and self.session:
            query = select(CodeSnippet).where(
                CodeSnippet.id == snippet_id,
                CodeSnippet.user_id == user_id,
            )
            res = await self.session.execute(query)
            snip = res.scalar_one_or_none()
            if not snip:
                return None

            if title is not None:
                snip.title = title
            if language is not None:
                snip.language = language.lower()
            if code is not None:
                snip.code = code
            if description is not None:
                snip.description = description
            if tags is not None:
                snip.tags = ",".join(tags) if tags else None
            if is_favorite is not None:
                snip.is_favorite = is_favorite
            snip.updated_at = now

            await self.session.commit()
            await self.session.refresh(snip)
            return snip.to_dict()

        with _MEM_LOCK:
            snip_dict = _MEM_SNIPPETS.get(snippet_id)
            if not snip_dict or snip_dict["user_id"] != user_id:
                return None

            if title is not None:
                snip_dict["title"] = title
            if language is not None:
                snip_dict["language"] = language.lower()
            if code is not None:
                snip_dict["code"] = code
            if description is not None:
                snip_dict["description"] = description
            if tags is not None:
                snip_dict["tags"] = tags
            if is_favorite is not None:
                snip_dict["is_favorite"] = is_favorite
            snip_dict["updated_at"] = now.isoformat()

            return dict(snip_dict)

    async def delete_snippet(self, user_id: str, snippet_id: str) -> bool:
        """Delete snippet with strict ownership guard."""
        if self._use_db and self.session:
            query = select(CodeSnippet).where(
                CodeSnippet.id == snippet_id,
                CodeSnippet.user_id == user_id,
            )
            res = await self.session.execute(query)
            snip = res.scalar_one_or_none()
            if not snip:
                return False

            await self.session.delete(snip)
            await self.session.commit()
            return True

        with _MEM_LOCK:
            snip_dict = _MEM_SNIPPETS.get(snippet_id)
            if not snip_dict or snip_dict["user_id"] != user_id:
                return False
            del _MEM_SNIPPETS[snippet_id]
            return True

    # ---------------------------------------------------------------------------
    # Code Executions
    # ---------------------------------------------------------------------------

    async def create_execution(
        self,
        user_id: str,
        language: str,
        code: str,
        stdin: str | None = None,
        snippet_id: str | None = None,
        status: str = "success",
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        execution_time_ms: int = 0,
    ) -> dict[str, Any]:
        """Record a sandboxed code execution run."""
        now = datetime.now(UTC)
        exec_id = str(uuid.uuid4())

        if self._use_db and self.session:
            ex = CodeExecution(
                id=exec_id,
                user_id=user_id,
                snippet_id=snippet_id,
                language=language.lower(),
                code=code,
                stdin=stdin,
                status=status,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                execution_time_ms=execution_time_ms,
                created_at=now,
            )
            self.session.add(ex)
            await self.session.commit()
            await self.session.refresh(ex)
            return ex.to_dict()

        data: dict[str, Any] = {
            "id": exec_id,
            "user_id": user_id,
            "snippet_id": snippet_id,
            "language": language.lower(),
            "code": code,
            "stdin": stdin,
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "execution_time_ms": execution_time_ms,
            "created_at": now.isoformat(),
        }
        with _MEM_LOCK:
            _MEM_EXECUTIONS[exec_id] = data
        return dict(data)

    async def list_executions(
        self,
        user_id: str,
        snippet_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List past executions for a user with optional snippet_id filter."""
        if self._use_db and self.session:
            query = select(CodeExecution).where(CodeExecution.user_id == user_id)
            if snippet_id:
                query = query.where(CodeExecution.snippet_id == snippet_id)

            count_query = select(func.count()).select_from(query.subquery())
            total_res = await self.session.execute(count_query)
            total = total_res.scalar() or 0

            query = query.order_by(desc(CodeExecution.created_at)).limit(limit).offset(offset)
            res = await self.session.execute(query)
            return [e.to_dict() for e in res.scalars().all()], total

        with _MEM_LOCK:
            matched = [
                dict(e)
                for e in _MEM_EXECUTIONS.values()
                if e["user_id"] == user_id and (not snippet_id or e.get("snippet_id") == snippet_id)
            ]
            matched.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            return matched[offset : offset + limit], len(matched)

    async def get_execution(self, user_id: str, execution_id: str) -> dict[str, Any] | None:
        """Get single execution record with strict user_id check."""
        if self._use_db and self.session:
            query = select(CodeExecution).where(
                CodeExecution.id == execution_id,
                CodeExecution.user_id == user_id,
            )
            res = await self.session.execute(query)
            ex = res.scalar_one_or_none()
            return ex.to_dict() if ex else None

        with _MEM_LOCK:
            ex_dict = _MEM_EXECUTIONS.get(execution_id)
            if ex_dict and ex_dict["user_id"] == user_id:
                return dict(ex_dict)
            return None

    # ---------------------------------------------------------------------------
    # Analytics / Stats
    # ---------------------------------------------------------------------------

    async def get_user_stats(self, user_id: str) -> dict[str, Any]:
        """Compute developer studio statistics for a user."""
        snippets, total_snippets = await self.list_snippets(user_id, limit=1000)
        executions, total_executions = await self.list_executions(user_id, limit=1000)

        favorite_count = sum(1 for s in snippets if s.get("is_favorite"))
        languages_count: dict[str, int] = {}
        for s in snippets:
            lang = s.get("language") or "other"
            languages_count[lang] = languages_count.get(lang, 0) + 1

        successful_executions = sum(1 for e in executions if e.get("status") == "success" and e.get("exit_code") == 0)
        success_rate = (
            round((successful_executions / total_executions) * 100, 1)
            if total_executions > 0
            else 100.0
        )

        return {
            "total_snippets": total_snippets,
            "favorite_snippets": favorite_count,
            "languages_count": languages_count,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "success_rate_percentage": success_rate,
        }
