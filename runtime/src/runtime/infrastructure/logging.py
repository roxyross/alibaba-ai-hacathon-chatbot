"""structlog configuration for the runtime.

Mirrors the convention established in `backend/src/app/logging.py` so
logs from both services have the same JSON shape and are aggregated
the same way by the observability stack.

Two prerequisites that have bitten the project before:

  1. The stdlib root logger must have a handler attached. Without one,
     structlog's `LoggerFactory` emits records into the void.
  2. The stdlib root logger's effective level must allow INFO. The
     default is WARNING (30); structlog's `filter_by_level` is a
     structlog-layer filter and does NOT replace the stdlib-side check.

Both are set here, idempotently.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", as_json: bool = True) -> None:
    """Configure structlog and the stdlib root logger.

    Safe to call multiple times; later calls win. The runtime calls
    this once at startup.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    if not logging.getLogger().handlers:
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    logging.getLogger().setLevel(log_level)

    processors: list = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    if as_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Module-level log — most callers will use `from runtime.logging import log`.
log = structlog.get_logger()
