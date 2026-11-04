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
    # Main client
    "MTNCloud",
    "MtnCloudClient",
    "MtnCloudError",
    "ModernTimeoutError",
    "TransportError",
    # Configuration
    "MTNCloudConfig",
    "ClientSettings",
    # Exceptions
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
    "__version__",
]
