"""ASGI Middleware for Correlation IDs, Distributed Tracing, and Latency Metrics."""

from __future__ import annotations

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.correlation import (
    TraceCollector,
    TraceRecord,
    correlation_id_ctx,
    parent_span_id_ctx,
    span_id_ctx,
    trace_id_ctx,
)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Propagates Correlation IDs and root trace context across all API requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.time()

        # 1. Extract or generate Correlation ID
        correlation_id = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or f"cid_{uuid.uuid4().hex[:16]}"
        )

        # 2. Extract or generate Trace ID (supporting W3C traceparent if present)
        traceparent = request.headers.get("traceparent")
        if traceparent and len(traceparent.split("-")) >= 4:
            parts = traceparent.split("-")
            trace_id = f"tr_{parts[1]}"
            parent_span_id = f"sp_{parts[2]}"
        else:
            trace_id = request.headers.get("x-trace-id") or f"tr_{uuid.uuid4().hex[:24]}"
            parent_span_id = None

        root_span_id = f"sp_{uuid.uuid4().hex[:16]}"

        # 3. Bind context variables for async execution tree
        token_cid = correlation_id_ctx.set(correlation_id)
        token_tid = trace_id_ctx.set(trace_id)
        token_sid = span_id_ctx.set(root_span_id)
        token_parent = parent_span_id_ctx.set(parent_span_id)

        # 4. Initialize Root Trace Record
        root_trace = TraceRecord(
            trace_id=trace_id,
            correlation_id=correlation_id,
            root_span_name=f"{request.method} {request.url.path}",
            start_time=start_time,
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.path": request.url.path,
                "client.host": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", "unknown"),
            },
        )
        TraceCollector.get_instance().record_trace(root_trace)

        status_code = 500
        error_msg = None

        response: Response | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            end_time = time.time()
            duration_ms = round((end_time - start_time) * 1000.0, 2)

            root_trace.end_time = end_time
            root_trace.duration_ms = duration_ms
            root_trace.status = "error" if status_code >= 400 or error_msg else "ok"
            root_trace.attributes["http.status_code"] = status_code
            if error_msg:
                root_trace.attributes["error"] = error_msg

            # Clean contextvars
            correlation_id_ctx.reset(token_cid)
            trace_id_ctx.reset(token_tid)
            span_id_ctx.reset(token_sid)
            parent_span_id_ctx.reset(token_parent)

        assert response is not None
        response.headers["x-correlation-id"] = correlation_id
        response.headers["x-trace-id"] = trace_id
        response.headers["x-response-time-ms"] = str(duration_ms)
        return response
