"""Exit codes and error documents for the mtncloud CLI."""

from __future__ import annotations

from typing import Any

from mtn_cloud.modern_exceptions import (
    AuthenticationError,
    ForbiddenError,
    MtnCloudError,
    NotFoundError,
)

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_PARTIAL = 3
EXIT_NOT_FOUND = 4
EXIT_AMBIGUOUS = 5
EXIT_AUTH = 6
EXIT_API = 7
EXIT_INTERRUPTED = 130

ERROR_SCHEMA = "mtncloud.error/v1"


class AmbiguousNameError(Exception):
    """A name matched several resources, or a scope name could not be resolved uniquely."""


class MissingCredentialsError(Exception):
    """No API token is configured; detected before any request is made."""

    def __init__(self, message: str = "No credentials configured. Set MTN_CLOUD_TOKEN.") -> None:
        super().__init__(message)


def exit_code_for(exc: BaseException) -> int:
    """Map an exception to a process exit code. This is the single mapping."""
    if isinstance(exc, KeyboardInterrupt):
        return EXIT_INTERRUPTED
    if isinstance(exc, MissingCredentialsError):
        return EXIT_AUTH
    if isinstance(exc, (AuthenticationError, ForbiddenError)):
        return EXIT_AUTH
    # NotFoundError must precede any ValueError handling: LookupNotFoundError is both.
    if isinstance(exc, NotFoundError):
        return EXIT_NOT_FOUND
    if isinstance(exc, AmbiguousNameError):
        return EXIT_AMBIGUOUS
    if isinstance(exc, MtnCloudError):
        return EXIT_API
    return EXIT_INTERNAL


def error_document(exc: BaseException) -> dict[str, Any]:
    """Build the ``mtncloud.error/v1`` document from sanitized fields only."""
    if isinstance(exc, MtnCloudError):
        message = exc.message
    else:
        message = str(exc)
    return {
        "schema": ERROR_SCHEMA,
        "error": {
            "type": type(exc).__name__,
            "message": message,
            "status_code": getattr(exc, "status_code", None),
            "request_id": getattr(exc, "request_id", None),
            "method": getattr(exc, "method", None),
            "path": getattr(exc, "path", None),
        },
    }
