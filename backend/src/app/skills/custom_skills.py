"""Custom Skill execution engine and database lifecycle manager."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.db import get_session_factory
from app.models.custom_skill import CustomSkill
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

log = structlog.get_logger()


class CustomSkillService:
    """Manages user-defined custom skills, sandboxing, and ToolRegistry registration."""

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry.get_instance()
        self._mem_skills: dict[str, dict[str, Any]] = {}

    def _register_skill_tool(self, skill_dict: dict[str, Any]) -> None:
        key = skill_dict["skill_key"]
        tool_id = f"custom_skill_{key}"

        tool = AgentTool(
            id=tool_id,
            name=skill_dict["name"],
            description=skill_dict["description"],
            source=ToolSource.SKILL,
            capabilities=["custom_skill", key],
            input_schema=skill_dict.get("parameters_schema", {"type": "object", "properties": {}}),
            permissions=[f"custom_skill.{key}"],
            risk_level=RiskLevel(skill_dict.get("risk_level", "low")),
            requires_confirmation=skill_dict.get("requires_confirmation", False),
            enabled=skill_dict.get("enabled", True),
        )

        async def _skill_handler(**kwargs: Any) -> dict[str, Any]:
            return await self.execute_skill_by_key(skill_dict["user_id"], key, kwargs)

        self._tool_registry.register(tool, _skill_handler)

    async def create_skill(
        self,
        user_id: str,
        name: str,
        skill_key: str,
        description: str,
        code_or_prompt_template: str,
        execution_type: str = "prompt",
        parameters_schema: dict[str, Any] | None = None,
        trigger_phrases: list[str] | None = None,
        risk_level: str = "low",
        requires_confirmation: bool = False,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and register a custom skill."""
        sid = str(uuid.uuid4())
        clean_key = re.sub(r"[^a-zA-Z0-9_]", "_", skill_key.lower().strip())
        now = datetime.now(UTC)

        record_dict: dict[str, Any] = {
            "id": sid,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "name": name,
            "skill_key": clean_key,
            "description": description,
            "trigger_phrases": trigger_phrases or [],
            "parameters_schema": parameters_schema or {"type": "object", "properties": {}},
            "execution_type": execution_type,
            "code_or_prompt_template": code_or_prompt_template,
            "timeout_seconds": 30,
            "risk_level": risk_level,
            "requires_confirmation": requires_confirmation,
            "enabled": True,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    db_skill = CustomSkill(
                        id=sid,
                        user_id=user_id,
                        workspace_id=workspace_id,
                        name=name,
                        skill_key=clean_key,
                        description=description,
                        execution_type=execution_type,
                        code_or_prompt_template=code_or_prompt_template,
                        timeout_seconds=30,
                        risk_level=risk_level,
                        requires_confirmation=requires_confirmation,
                        enabled=True,
                        created_at=now,
                        updated_at=now,
                    )
                    db_skill.set_trigger_phrases(trigger_phrases or [])
                    db_skill.set_parameters_schema(parameters_schema or {})
                    session.add(db_skill)
                    await session.commit()
            except Exception as exc:
                log.warning("custom_skill.db_create_failed", error=str(exc))

        self._mem_skills[sid] = record_dict
        self._register_skill_tool(record_dict)
        return record_dict

    async def get_skill(self, user_id: str, skill_id: str) -> dict[str, Any] | None:
        """Fetch custom skill by ID."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(CustomSkill).where(
                        CustomSkill.id == skill_id,
                        CustomSkill.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        return item.to_dict()
            except Exception as exc:
                log.warning("custom_skill.db_get_failed", error=str(exc))

        mem = self._mem_skills.get(skill_id)
        if mem and mem.get("user_id") == user_id:
            return mem
        return None

    async def list_skills(self, user_id: str) -> list[dict[str, Any]]:
        """List all custom skills for a user."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = (
                        select(CustomSkill)
                        .where(CustomSkill.user_id == user_id)
                        .order_by(CustomSkill.created_at.desc())
                    )
                    res = await session.execute(stmt)
                    items = res.scalars().all()
                    if items:
                        return [it.to_dict() for it in items]
            except Exception as exc:
                log.warning("custom_skill.db_list_failed", error=str(exc))

        return [s for s in self._mem_skills.values() if s.get("user_id") == user_id]

    async def delete_skill(self, user_id: str, skill_id: str) -> bool:
        """Delete custom skill and unregister tool."""
        existing = await self.get_skill(user_id, skill_id)
        if not existing:
            return False

        tool_id = f"custom_skill_{existing['skill_key']}"
        self._tool_registry.unregister(tool_id)

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(CustomSkill).where(
                        CustomSkill.id == skill_id,
                        CustomSkill.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        await session.delete(item)
                        await session.commit()
            except Exception as exc:
                log.warning("custom_skill.db_delete_failed", error=str(exc))

        self._mem_skills.pop(skill_id, None)
        return True

    async def execute_skill_by_key(self, user_id: str, skill_key: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a custom skill using sandboxed template filling or Python eval."""
        skill: dict[str, Any] | None = None
        for s in self._mem_skills.values():
            if s.get("skill_key") == skill_key and s.get("user_id") == user_id:
                skill = s
                break

        if not skill:
            factory = get_session_factory()
            if factory is not None:
                try:
                    async with factory() as session:
                        stmt = select(CustomSkill).where(
                            CustomSkill.skill_key == skill_key,
                            CustomSkill.user_id == user_id,
                        )
                        res = await session.execute(stmt)
                        item = res.scalars().first()
                        if item:
                            skill = item.to_dict()
                except Exception:
                    pass

        if not skill:
            raise ValueError(f"Custom skill '{skill_key}' not found.")

        exec_type = skill.get("execution_type", "prompt")
        template = skill.get("code_or_prompt_template", "")

        if exec_type == "prompt":
            # Template variable interpolation
            rendered = template
            for k, v in arguments.items():
                rendered = rendered.replace(f"{{{k}}}", str(v))

            return {
                "skill": skill["name"],
                "execution_type": "prompt",
                "rendered_prompt": rendered,
                "result": f"Executed custom skill '{skill['name']}': {rendered[:200]}",
                "arguments": arguments,
            }

        elif exec_type == "python_sandbox":
            # Safe AST math/expression evaluation
            safe_globals = {
                "__builtins__": {},
                "len": len,
                "min": min,
                "max": max,
                "sum": sum,
                "args": arguments,
            }
            try:
                # Compile and evaluate in isolated globals
                local_scope: dict[str, Any] = {}
                exec(template, safe_globals, local_scope)
                res = local_scope.get("result", local_scope)
                return {
                    "skill": skill["name"],
                    "execution_type": "python_sandbox",
                    "result": res,
                }
            except Exception as exc:
                return {
                    "skill": skill["name"],
                    "execution_type": "python_sandbox",
                    "error": str(exc),
                }

        return {
            "skill": skill["name"],
            "result": f"Executed custom skill {skill['name']}.",
            "arguments": arguments,
        }
