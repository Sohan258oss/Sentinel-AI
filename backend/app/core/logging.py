"""Structured logging.

JSON in production (machine-parseable for a real SOC), colourised key-value in
development. Incident and run identifiers are bound as context variables so
every log line emitted anywhere inside a graph run is automatically correlated.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.config import settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    # Third-party libraries are chatty; keep the operator feed readable.
    for noisy in ("httpx", "httpcore", "chromadb", "urllib3", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.env == "production"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)  # type: ignore[return-value]


class run_context:
    """Bind incident/run identifiers for the duration of a block.

    Usage::

        with run_context(incident_id="INC-1", run_id="abc"):
            ...  # every log line inside carries both ids
    """

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = {k: v for k, v in kwargs.items() if v is not None}

    def __enter__(self) -> "run_context":
        bind_contextvars(**self._kwargs)
        return self

    def __exit__(self, *exc: object) -> None:
        clear_contextvars()
