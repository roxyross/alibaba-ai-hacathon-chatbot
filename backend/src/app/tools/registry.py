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
    ToolExecutionError,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolSource,
    ToolVerificationResult,
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
        if tool_id in self._tools:
            return self._tools[tool_id]
        if f"system_{tool_id}" in self._tools:
            return self._tools[f"system_{tool_id}"]
        if tool_id.startswith("system_") and tool_id[7:] in self._tools:
            return self._tools[tool_id[7:]]
        return None

    def get_handler(self, tool_id: str) -> Callable[..., Coroutine[Any, Any, Any]] | None:
        """Retrieve tool execution handler by ID."""
        if tool_id in self._handlers:
            return self._handlers[tool_id]
        if f"system_{tool_id}" in self._handlers:
            return self._handlers[f"system_{tool_id}"]
        if tool_id.startswith("system_") and tool_id[7:] in self._handlers:
            return self._handlers[tool_id[7:]]
        return None

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

    async def execute(
        self,
        request: ToolExecutionRequest,
        _trusted_internal: bool = True,
    ) -> ToolExecutionResult:
        """Execute a tool handler with execution boundary permission enforcement and error trapping."""
        # External callers cannot use bypass_confirmation
        if not _trusted_internal:
            request.bypass_confirmation = False

        tool = self.get(request.tool_id)
        if not tool:
            return ToolExecutionResult(
                tool_id=request.tool_id,
                target_app=request.target_app,
                target_device=request.target_device,
                success=False,
                status=ToolExecutionStatus.UNSUPPORTED,
                error=f"Tool '{request.tool_id}' is not registered in the Tool Registry.",
                error_details=ToolExecutionError(
                    code="tool_not_found",
                    message=f"Tool '{request.tool_id}' is not registered in the Tool Registry.",
                    retryable=False,
                ),
            )
        if not tool.enabled:
            return ToolExecutionResult(
                tool_id=request.tool_id,
                target_app=request.target_app,
                target_device=request.target_device,
                success=False,
                status=ToolExecutionStatus.DENIED,
                error=f"Tool '{request.tool_id}' is currently disabled.",
                error_details=ToolExecutionError(
                    code="tool_disabled",
                    message=f"Tool '{request.tool_id}' is currently disabled.",
                    retryable=False,
                ),
            )

        handler = self.get_handler(request.tool_id)
        if not handler:
            return ToolExecutionResult(
                tool_id=request.tool_id,
                target_app=request.target_app,
                target_device=request.target_device,
                success=False,
                status=ToolExecutionStatus.UNSUPPORTED,
                error=f"No execution handler configured for tool '{request.tool_id}'.",
                error_details=ToolExecutionError(
                    code="handler_missing",
                    message=f"No execution handler configured for tool '{request.tool_id}'.",
                    retryable=False,
                ),
            )

        # ---------------------------------------------------------------------
        # Execution Boundary Permission Enforcement
        # ---------------------------------------------------------------------
        if not request.user_id:
            return ToolExecutionResult(
                tool_id=request.tool_id,
                target_app=request.target_app,
                target_device=request.target_device,
                success=False,
                status=ToolExecutionStatus.DENIED,
                error="Missing user_id for authenticated tool execution.",
                error_details=ToolExecutionError(
                    code="unauthenticated",
                    message="Missing user_id for authenticated tool execution.",
                    retryable=False,
                ),
            )

        # Lazy import to avoid circular dependency
        from app.permissions.service import PermissionService

        perm_service = PermissionService()
        perm_res = await perm_service.check_permission(
            user_id=request.user_id,
            tool_id=request.tool_id,
            target_app=request.target_app,
            device_id=request.target_device,
            parameters=request.arguments,
        )

        if not perm_res.granted:
            if perm_res.requires_confirmation:
                if _trusted_internal and request.bypass_confirmation:
                    # Authorized internal service boundary bypass
                    pass
                elif request.confirmation_token:
                    # Validate and consume token via central ConfirmationGate
                    from app.trust.confirmation_gate import ConfirmationGate, canonicalize_parameters
                    params_hash = canonicalize_parameters(request.arguments)
                    ok, msg, rec = ConfirmationGate.consume_challenge(
                        challenge_id_or_token=request.confirmation_token,
                        user_id=request.user_id,
                        action_type=request.tool_id,
                        details_match={"parameters_hash": params_hash},
                    )
                    if not ok:
                        return ToolExecutionResult(
                            tool_id=request.tool_id,
                            target_app=request.target_app,
                            target_device=request.target_device,
                            success=False,
                            status=ToolExecutionStatus.REQUIRES_CONFIRMATION,
                            error=f"Confirmation rejected: {msg}",
                            error_details=ToolExecutionError(
                                code="invalid_confirmation",
                                message=f"Confirmation rejected: {msg}",
                                retryable=False,
                            ),
                        )
                else:
                    from app.trust.confirmation_gate import ConfirmationGate, canonicalize_parameters
                    from app.trust.schemas import RiskTier
                    params_hash = canonicalize_parameters(request.arguments)
                    tier = RiskTier.HIGH
                    if tool.risk_level.value in [r.value for r in RiskTier]:
                        tier = RiskTier(tool.risk_level.value)
                    chal = ConfirmationGate.create_challenge(
                        user_id=request.user_id,
                        action_type=request.tool_id,
                        title=f"Execute tool: {tool.name}",
                        summary=perm_res.reason or f"Action requires explicit user confirmation for '{tool.name}'.",
                        details={
                            "tool_id": request.tool_id,
                            "target_app": request.target_app,
                            "target_device": request.target_device,
                            "parameters_hash": params_hash,
                            "arguments": request.arguments,
                        },
                        risk_tier=tier,
                        risk_score=85 if tool.risk_level == RiskLevel.CRITICAL else 70,
                        requires_2fa=(tool.risk_level == RiskLevel.CRITICAL),
                    )
                    return ToolExecutionResult(
                        tool_id=request.tool_id,
                        target_app=request.target_app,
                        target_device=request.target_device,
                        success=False,
                        status=ToolExecutionStatus.REQUIRES_CONFIRMATION,
                        error=perm_res.reason or f"Action requires explicit user confirmation for '{tool.name}'.",
                        error_details=ToolExecutionError(
                            code="requires_confirmation",
                            message=perm_res.reason or f"Action requires explicit user confirmation for '{tool.name}'.",
                            retryable=True,
                        ),
                        output={"challenge": chal.model_dump()},
                    )
            else:
                return ToolExecutionResult(
                    tool_id=request.tool_id,
                    target_app=request.target_app,
                    target_device=request.target_device,
                    success=False,
                    status=ToolExecutionStatus.DENIED,
                    error=perm_res.reason or f"Permission denied for tool '{tool.name}'.",
                    error_details=ToolExecutionError(
                        code="permission_denied",
                        message=perm_res.reason or f"Permission denied for tool '{tool.name}'.",
                        retryable=False,
                    ),
                )

        start = time.perf_counter()
        try:
            # Check parameters accepted by handler
            sig = inspect.signature(handler)
            kwargs: dict[str, Any] = {}
            args = request.arguments or getattr(request, "input", None) or {}
            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            for param_name in sig.parameters:
                if param_name in args:
                    kwargs[param_name] = args[param_name]
                elif param_name == "arguments":
                    param_type = sig.parameters[param_name].annotation
                    if param_type in (dict, "dict", "dict[str, Any]", Any) or isinstance(sig.parameters[param_name].default, dict):
                        kwargs["arguments"] = args
                    elif isinstance(args, dict) and "arguments" in args:
                        kwargs["arguments"] = args["arguments"]
                elif param_name == "user_id":
                    kwargs["user_id"] = request.user_id
                elif param_name == "workspace_id":
                    kwargs["workspace_id"] = request.workspace_id
                elif param_name == "task_id":
                    kwargs["task_id"] = request.task_id
                elif param_name == "step_id":
                    kwargs["step_id"] = request.step_id

            if has_var_keyword:
                for k, v in args.items():
                    if k not in kwargs:
                        kwargs[k] = v

            output = await handler(**kwargs)
            duration_ms = int((time.perf_counter() - start) * 1000)

            # Check if output explicitly signals a tool-level failure
            if isinstance(output, dict) and output.get("isError") is True:
                err_content = output.get("content") or output.get("error") or "Tool returned an error."
                return ToolExecutionResult(
                    tool_id=request.tool_id,
                    target_app=request.target_app,
                    target_device=request.target_device,
                    success=False,
                    status=ToolExecutionStatus.FAILED,
                    output=output,
                    error=str(err_content),
                    error_details=ToolExecutionError(
                        code=str(output.get("code", "tool_error")),
                        message=str(err_content),
                        retryable=bool(output.get("retryable", False)),
                    ),
                    duration_ms=duration_ms,
                )

            return ToolExecutionResult(
                tool_id=request.tool_id,
                target_app=request.target_app,
                target_device=request.target_device,
                success=True,
                status=ToolExecutionStatus.COMPLETED,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolExecutionResult(
                tool_id=request.tool_id,
                target_app=request.target_app,
                target_device=request.target_device,
                success=False,
                status=ToolExecutionStatus.FAILED,
                error=str(exc),
                error_details=ToolExecutionError(
                    code="execution_exception",
                    message=str(exc),
                    retryable=False,
                ),
                duration_ms=duration_ms,
            )
