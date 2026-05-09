"""Structured logging setup for Aurelia.

`configure()` should be called once at startup. After that, modules use
``structlog.get_logger(__name__)`` to get a bound logger. In dev we render
human-friendly colored output; in prod we emit JSON for log aggregation.

Note: this module shadows the stdlib ``logging`` module name within the
``aurelia`` package, but only at the package level — the absolute import
``import logging`` below still resolves to the stdlib because Python 3 uses
absolute imports by default.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_configured = False


def configure(*, env: str = "dev", level: str = "INFO") -> None:
    """Configure structlog and the stdlib root logger.

    Idempotent: subsequent calls reconfigure with the new settings.

    Args:
        env: ``"dev"`` for colored console output, ``"prod"`` for JSON.
        level: Standard log level name (``"DEBUG"``, ``"INFO"``, etc.).
    """
    global _configured

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Wire stdlib logging at the desired level so third-party libs (LiveKit,
    # google-api-client) flow through our handlers.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if env == "prod":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str | None = None, **initial_values: Any) -> Any:
    """Return a bound structlog logger.

    If :func:`configure` has not yet run, falls back to defaults so importing
    code never crashes — but that path should not happen in normal startup.

    The return type is ``Any`` because structlog's bound-logger interface is
    runtime-dynamic — the wrapper class chosen at ``configure()`` time decides
    which methods exist. Callers should treat the result as a duck-typed
    logger with the standard ``debug/info/warning/error/bind`` methods.
    """
    if not _configured:
        configure()
    logger = structlog.get_logger(name)
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger
