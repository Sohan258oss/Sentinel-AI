"""Typed failures.

The graph must keep running when one agent fails — a partial operational
picture beats no picture at all. Typed exceptions let each node decide whether
to degrade, retry, or abort, instead of every caller guessing from a string.
"""

from __future__ import annotations


class SentinelError(Exception):
    """Base class for every error the platform raises deliberately."""

    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.recoverable = recoverable


class LLMUnavailableError(SentinelError):
    """No usable model — offline mode, missing key, or exhausted retries.

    Callers are expected to fall back to deterministic domain logic rather than
    propagate this to the operator.
    """


class StructuredOutputError(SentinelError):
    """The model answered, but not in the shape the contract requires."""


class ToolExecutionError(SentinelError):
    """A tool's live backend failed. Usually followed by a fallback."""

    def __init__(self, tool_name: str, message: str, *, recoverable: bool = True) -> None:
        super().__init__(f"[{tool_name}] {message}", recoverable=recoverable)
        self.tool_name = tool_name


class RetrievalError(SentinelError):
    """The vector store could not be queried."""


class VisionError(SentinelError):
    """Image analysis failed for a specific asset."""


class IncidentNotFoundError(SentinelError):
    def __init__(self, incident_id: str) -> None:
        super().__init__(f"Incident '{incident_id}' not found", recoverable=False)
        self.incident_id = incident_id


class ConfigurationError(SentinelError):
    """Misconfiguration that cannot be recovered from at runtime."""

    def __init__(self, message: str) -> None:
        super().__init__(message, recoverable=False)
