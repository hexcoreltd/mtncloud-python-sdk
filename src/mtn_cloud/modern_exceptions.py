"""Exception types for the modern client foundation."""

from typing import Any


class MtnCloudError(Exception):
    """Base class for all modern SDK errors.

    Errors raised by the request pipeline also record the operation that
    failed: the HTTP ``method``, the request ``path`` without its query
    string, and the number of HTTP ``attempts`` made, including retries.
    These fields are ``None`` for errors raised outside the pipeline.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
        request_id: str | None = None,
        method: str | None = None,
        path: str | None = None,
        attempts: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response
        self.request_id = request_id
        self.method = method
        self.path = path
        self.attempts = attempts

    def __str__(self) -> str:
        suffix = f" (HTTP {self.status_code})" if self.status_code else ""
        details = []
        if self.method and self.path:
            details.append(f"{self.method} {self.path}")
        if self.request_id:
            details.append(f"request_id={self.request_id}")
        if self.attempts is not None and self.attempts > 1:
            details.append(f"attempts={self.attempts}")
        context = f" [{', '.join(details)}]" if details else ""
        return f"{self.message}{suffix}{context}"


class AuthenticationError(MtnCloudError):
    """The request was not authenticated."""


class ForbiddenError(MtnCloudError):
    """The credential is valid but not permitted to perform the request."""


class NotFoundError(MtnCloudError):
    """The requested resource does not exist."""


class LookupNotFoundError(NotFoundError, ValueError):
    """A client-side lookup within a verified collection found no match.

    Also a ``ValueError`` so callers written against earlier releases, where
    these lookups raised ``ValueError``, keep working.
    """


class ConflictError(MtnCloudError):
    """The request conflicts with the current state of the resource."""


class ValidationError(MtnCloudError):
    """The service rejected the request as invalid."""


class RateLimitError(MtnCloudError):
    """The service rate-limited the request."""


class ServerError(MtnCloudError):
    """The service returned a server-side error."""


class TransportError(MtnCloudError):
    """The request could not reach the MTN Cloud API."""


class TimeoutError(MtnCloudError):
    """An operation did not reach its target state before its deadline."""

    def __init__(self, message: str, *, timeout: float, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.timeout = timeout
