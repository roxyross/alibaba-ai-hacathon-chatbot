"""Centralised structlog configuration.

Imported by `app.main` as the very first thing so that any module-level
`structlog.get_logger()` (e.g. in `app.auth.email`) sees the configured
renderers. Without this ordering, `cache_logger_on_first_use=True` would
freeze loggers in the default (stderr-only) renderer before the JSON
renderer is configured — which makes dev-mode "magic-link printed to log"
silently invisible.

Why this lives in its own module:

  - The configure call must run before any other `app.*` import that
    captures a logger at module scope.
  - Putting the call in `app.main` works ONLY if `app.main` is the entry
    point — but uvicorn's reload worker spawns a child that re-runs
    `app.main`, and the re-import order is not guaranteed to be
    `app.main` first.
  - Importing `app.logging` from a side-effect-free module guarantees
    the configure runs at the first import of any submodule that needs
    logging.
"""

from __future__ import annotations

import logging
import sys

import structlog

# `structlog.stdlib.LoggerFactory()` returns a stdlib `logging.Logger`.
# Two stdlib-side prerequisites for the dev-mode "magic-link printed to
# log" line to actually surface in captured stdout:
#   1. The stdlib root logger must have a handler installed.
#   2. The root logger's effective level must allow INFO (otherwise
#      stdlib silently drops records before our handler sees them).
# structlog's `filter_by_level` is a structlog-layer filter; it does NOT
# replace the stdlib-side level check that happens inside `logger.info()`.
if not logging.getLogger().handlers:
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
logging.getLogger().setLevel(logging.INFO)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

__all__ = ["structlog"]
