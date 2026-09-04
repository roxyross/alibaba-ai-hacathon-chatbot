"""ROXY JARVIS AI Gateway — multi-provider abstraction layer."""

# Configure structlog at package import time so any module that captures
# a logger at module scope (e.g. `log = structlog.get_logger()` at the
# top of `app.auth.email`) sees the configured renderer. Without this,
# `cache_logger_on_first_use=True` would freeze loggers in the default
# renderer before the JSON renderer is configured — making dev-mode
# "magic-link printed to log" silently invisible in the captured stdout.
#
# This must run before any submodule that does `structlog.get_logger()`
# at module scope. Python guarantees `app/__init__.py` runs first when
# any submodule of `app` is imported, so this is the right place.
from . import logging as _logging  # noqa: F401 — side-effect import

__version__ = "0.1.0"
