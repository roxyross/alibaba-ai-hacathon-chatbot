"""Central Tool Registry implementation for ROXY-AI 2.0.

Provides dynamic tool discovery, capability lookup, risk classification,
and sandboxed execution dispatching.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Coroutine
from typing import Any

from app.tools.schemas import (
    AgentTool,
    RiskLevel,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolSource,
)


class ToolRegistry:
    """Singleton registry managing all executable tools from system, skills, connectors, and MCP."""

    _instance: ToolRegistry | None = None

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def register(
        self,
        tool: AgentTool,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Register a tool and its asynchronous handler function."""
        self._tools[tool.id] = tool
        self._handlers[tool.id] = handler

    def unregister(self, tool_id: str) -> bool:
        """Remove a tool from the registry."""
        if tool_id in self._tools:
            del self._tools[tool_id]
            self._handlers.pop(tool_id, None)
            return True
        return False

    def get(self, tool_id: str) -> AgentTool | None:
        """Retrieve tool specification by ID."""
        return self._tools.get(tool_id)

    def get_handler(self, tool_id: str) -> Callable[..., Coroutine[Any, Any, Any]] | None:
        """Retrieve tool execution handler by ID."""
        return self._handlers.get(tool_id)

    def list_tools(
        self,
        source: ToolSource | None = None,
        capability: str | None = None,
        risk_level: RiskLevel | None = None,
        enabled_only: bool = True,
    ) -> list[AgentTool]:
        """List registered tools matching optional filters."""
        tools = list(self._tools.values())
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        if source:
            tools = [t for t in tools if t.source == source]
        if risk_level:
            tools = [t for t in tools if t.risk_level == risk_level]
        if capability:
            cap_lower = capability.lower()
            tools = [t for t in tools if any(cap_lower in c.lower() for c in t.capabilities)]
        return tools

    def list_all(self) -> list[AgentTool]:
        """Convenience method returning all registered tools."""
        return list(self._tools.values())

    def search_tools(self, query: str) -> list[AgentTool]:
        """Search tools by name, description, or capability tags."""
        q = query.lower().strip()
        if not q:
            return list(self._tools.values())
        matches: list[AgentTool] = []
        for t in self._tools.values():
            if not t.enabled:
                continue
            if (
                q in t.id.lower()
                or q in t.name.lower()
                or q in t.description.lower()
                or any(q in c.lower() for c in t.capabilities)
            ):
                matches.append(t)
        return matches

    def discover_for_task(self, objective: str, user_id: str | None = None) -> list[AgentTool]:
        """Dynamically discover available tools relevant to a task objective."""
        obj_lower = objective.lower()
        scored: list[tuple[int, AgentTool]] = []

        keywords_map: dict[str, list[str]] = {
            "math": ["calculate", "math", "sum", "multiply", "divide", "add", "equation", "number", "formula"],
            "search": ["search", "find", "lookup", "google", "web", "research", "news", "browse"],
            "email": ["email", "mail", "send", "message Ali", "draft", "inbox"],
            "job": ["schedule", "remind", "cron", "timer", "later", "daily", "weekly", "every day"],
            "memory": ["remember", "memory", "recall", "store", "save fact", "fact"],
            "document": ["pdf", "document", "docx", "file", "vault", "knowledge", "read doc"],
            "code": ["code", "python", "script", "program", "execute", "run"],
            "browser": ["browse", "browser", "navigate", "website", "web page", "scrape", "extract", "form", "fill", "screenshot"],
        }

        for tool in self._tools.values():
            if not tool.enabled:
                continue
            score = 0
            # Check capability overlap
            for cap in tool.capabilities:
                if cap.lower() in obj_lower:
                    score += 5
                related_kw = keywords_map.get(cap.lower(), [])
                for kw in related_kw:
                    if kw in obj_lower:
                        score += 3
            # Check description keywords
            words = [w for w in obj_lower.split() if len(w) > 3]
            for w in words:
                if w in tool.name.lower() or w in tool.description.lower():
                    score += 2

            # Always give a base score to system utilities if no specific matches
            if score > 0:
                scored.append((score, tool))

        # Sort by relevance score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [t for _, t in scored]
        # If no specific matches found, return general default system tools
        if not results:
            results = [t for t in self._tools.values() if t.enabled][:5]
        return results

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute a tool handler with execution timing, error trapping, and verification."""
        tool = self.get(request.tool_id)
        if not tool:
            return ToolExecutionResult(
                tool_id=request.tool_id,
                success=False,
                error=f"Tool '{request.tool_id}' is not registered in the Tool Registry.",
            )
        if not tool.enabled:
            return ToolExecutionResult(
                tool_id=request.tool_id,
                success=False,
                error=f"Tool '{request.tool_id}' is currently disabled.",
            )

        handler = self.get_handler(request.tool_id)
        if not handler:
            return ToolExecutionResult(
                tool_id=request.tool_id,
                success=False,
                error=f"No execution handler configured for tool '{request.tool_id}'.",
            )

        start = time.perf_counter()
        try:
            # Check parameters accepted by handler
            sig = inspect.signature(handler)
            kwargs: dict[str, Any] = {}
            args = request.arguments or getattr(request, "input", None) or {}
            for param_name in sig.parameters:
                if param_name in args:
                    kwargs[param_name] = args[param_name]
                elif param_name == "arguments":
                    kwargs["arguments"] = args
                elif param_name == "user_id":
                    kwargs["user_id"] = request.user_id
                elif param_name == "workspace_id":
                    kwargs["workspace_id"] = request.workspace_id
                elif param_name == "task_id":
                    kwargs["task_id"] = request.task_id
                elif param_name == "step_id":
                    kwargs["step_id"] = request.step_id

            output = await handler(**kwargs)
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolExecutionResult(
                tool_id=request.tool_id,
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolExecutionResult(
                tool_id=request.tool_id,
                success=False,
                error=str(exc),
                duration_ms=duration_ms,
            )
