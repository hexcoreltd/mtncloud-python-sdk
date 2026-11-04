"""Public package exports for the MTN Cloud Python SDK."""

from mtn_cloud._version import __version__
from mtn_cloud.client import MTNCloud
from mtn_cloud.config import MTNCloudConfig
from mtn_cloud.exceptions import (
    AuthenticationError,
    ForbiddenError,
    MTNCloudError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ResourceConflictError,
    ServerError,
    TimeoutError,
    ValidationError,
)
from mtn_cloud.modern_client import MtnCloudClient
from mtn_cloud.modern_exceptions import MtnCloudError, TransportError
from mtn_cloud.modern_exceptions import TimeoutError as ModernTimeoutError
from mtn_cloud.settings import ClientSettings

__author__ = "Hexcore Ltd"
__license__ = "MIT"
__all__ = [
    "__version__",
    # Modern client (recommended for new integrations).
    "MtnCloudClient",
    "ClientSettings",
    # Modern exceptions. ``ModernTimeoutError`` is
    # ``mtn_cloud.modern_exceptions.TimeoutError``, renamed so it does not
    # shadow the built-in. Prefer importing from ``mtn_cloud.modern_exceptions``.
    "MtnCloudError",
    "TransportError",
    "ModernTimeoutError",
    # Legacy client, kept for compatibility. Note the casing: ``MTNCloudError``
    # is the legacy base class; ``MtnCloudError`` above is the modern one.
    "MTNCloud",
    "MTNCloudConfig",
    "MTNCloudError",
    "AuthenticationError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "ServerError",
    "ForbiddenError",
    "TimeoutError",
    "QuotaExceededError",
    "ResourceConflictError",
]
