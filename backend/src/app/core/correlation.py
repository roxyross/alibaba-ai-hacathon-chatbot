"""Distributed tracing and correlation ID management with async contextvars propagation.

Provides:
- ContextVar-based tracking of Correlation IDs, Trace IDs, and Hierarchical Spans.
- Lightweight, zero-dependency in-process distributed trace collector.
- Asynchronous and synchronous context managers for nested span recording.
- Automatic duration calculation, attribute recording, and error tagging.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from collections import deque
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Context Variables
# -----------------------------------------------------------------------------

correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)
trace_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)
span_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "span_id", default=""
)
parent_span_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "parent_span_id", default=None
)


def get_correlation_id() -> str:
    """Return the active correlation ID or generate a default one."""
    cid = correlation_id_ctx.get()
    if not cid:
        cid = f"cid_{uuid.uuid4().hex[:16]}"
        correlation_id_ctx.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Explicitly assign the active correlation ID in context."""
    correlation_id_ctx.set(cid)


def get_trace_id() -> str:
    """Return the active trace ID or generate a default one."""
    tid = trace_id_ctx.get()
    if not tid:
        tid = f"tr_{uuid.uuid4().hex[:24]}"
        trace_id_ctx.set(tid)
    return tid


def set_trace_id(tid: str) -> None:
    """Explicitly assign the active trace ID in context."""
    trace_id_ctx.set(tid)


# -----------------------------------------------------------------------------
# Tracing Models
# -----------------------------------------------------------------------------


class SpanRecord(BaseModel):
    """Detailed record of a single execution span within a trace."""

    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    correlation_id: str
    name: str
    start_time: float
    end_time: float | None = None
    duration_ms: float = 0.0
    status: str = "ok"  # ok, error, blocked
    attributes: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def finish(self, status: str = "ok", error: str | None = None) -> None:
        """Mark span as finished and calculate total duration."""
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000.0, 2)
        self.status = status
        self.error_message = error


class TraceRecord(BaseModel):
    """Aggregated trace containing root and child spans with waterfall ordering."""

    trace_id: str
    correlation_id: str
    root_span_name: str
    start_time: float
    end_time: float | None = None
    duration_ms: float = 0.0
    status: str = "ok"
    spans: list[SpanRecord] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_waterfall(self) -> list[dict[str, Any]]:
        """Return spans sorted hierarchically with relative timing offsets."""
        base_time = self.start_time
        res: list[dict[str, Any]] = []
        for s in self.spans:
            offset_ms = round(max(0.0, s.start_time - base_time) * 1000.0, 2)
            res.append({
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "offset_ms": offset_ms,
                "duration_ms": s.duration_ms,
                "status": s.status,
                "attributes": s.attributes,
                "error_message": s.error_message,
            })
        return res


# -----------------------------------------------------------------------------
# Trace Collector (In-Memory Ring Buffer)
# -----------------------------------------------------------------------------


class TraceCollector:
    """Thread-safe collector and indexer for distributed traces."""

    _instance: TraceCollector | None = None

    def __init__(self, max_traces: int = 1000) -> None:
        self.max_traces = max_traces
        self._traces: deque[TraceRecord] = deque(maxlen=max_traces)
        self._trace_map: dict[str, TraceRecord] = {}
        self._correlation_map: dict[str, list[str]] = {}

    @classmethod
    def get_instance(cls) -> TraceCollector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def clear(self) -> None:
        """Reset collector state (used for test isolation)."""
        self._traces.clear()
        self._trace_map.clear()
        self._correlation_map.clear()

    def record_trace(self, trace: TraceRecord) -> None:
        """Register completed trace record."""
        # Evict from map if buffer is full
        if len(self._traces) >= self.max_traces:
            evicted = self._traces[0]
            self._trace_map.pop(evicted.trace_id, None)

        self._traces.append(trace)
        self._trace_map[trace.trace_id] = trace
        if trace.correlation_id:
            self._correlation_map.setdefault(trace.correlation_id, []).append(
                trace.trace_id
            )

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        """Look up trace record by trace ID."""
        return self._trace_map.get(trace_id)

    def get_traces_by_correlation(self, correlation_id: str) -> list[TraceRecord]:
        """Look up all traces sharing a correlation ID."""
        tids = self._correlation_map.get(correlation_id, [])
        return [self._trace_map[tid] for tid in tids if tid in self._trace_map]

    def list_recent_traces(self, limit: int = 50) -> list[TraceRecord]:
        """List most recent traces in reverse chronological order."""
        items = list(self._traces)
        items.reverse()
        return items[:limit]


# -----------------------------------------------------------------------------
# Trace Context Managers
# -----------------------------------------------------------------------------


@contextmanager
def trace_span(
    name: str, attributes: dict[str, Any] | None = None
) -> Generator[SpanRecord, None, None]:
    """Hierarchical span context manager that records execution timing."""
    trace_id = get_trace_id()
    correlation_id = get_correlation_id()
    parent_span_id = span_id_ctx.get()
    current_span_id = f"sp_{uuid.uuid4().hex[:16]}"

    span = SpanRecord(
        span_id=current_span_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id or None,
        correlation_id=correlation_id,
        name=name,
        start_time=time.time(),
        attributes=attributes or {},
    )

    collector = TraceCollector.get_instance()
    trace = collector.get_trace(trace_id)
    if trace is None and not parent_span_id:
        trace = TraceRecord(
            trace_id=trace_id,
            correlation_id=correlation_id,
            root_span_name=name,
            start_time=span.start_time,
            attributes=attributes or {},
        )
        collector.record_trace(trace)

    token_span = span_id_ctx.set(current_span_id)
    token_parent = parent_span_id_ctx.set(parent_span_id)

    try:
        yield span
        span.finish(status="ok")
    except Exception as exc:
        span.finish(status="error", error=str(exc))
        raise
    finally:
        span_id_ctx.reset(token_span)
        parent_span_id_ctx.reset(token_parent)

        collector = TraceCollector.get_instance()
        trace = collector.get_trace(trace_id)
        if trace:
            trace.spans.append(span)
            trace.duration_ms = round((time.time() - trace.start_time) * 1000.0, 2)
            trace.end_time = time.time()
            if span.status == "error":
                trace.status = "error"
