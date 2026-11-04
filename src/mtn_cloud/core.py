"""Core client behavior shared by service clients."""

import time
from collections.abc import Mapping
from typing import Any

import requests

from mtn_cloud.auth import CredentialProvider, StaticTokenProvider
from mtn_cloud.modern_exceptions import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    MtnCloudError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TransportError,
    ValidationError,
)
from mtn_cloud.settings import ClientSettings
from mtn_cloud.transport import HttpResponse, RequestsTransport, Transport


class CoreClient:
    """Authenticated request pipeline for the modern SDK."""

    def __init__(
        self,
        settings: ClientSettings,
        transport: Transport | None = None,
        credentials: CredentialProvider | None = None,
        sleeper: Any = time.sleep,
    ) -> None:
        self.settings = settings
        self.transport = transport or RequestsTransport(settings)
        self.credentials = credentials or StaticTokenProvider(settings.token_value())
        self._sleeper = sleeper

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        for attempt in range(self.settings.max_retries + 1):
            request_headers = dict(headers or {})
            token = self.credentials.get_token()
            if token:
                request_headers["Authorization"] = f"Bearer {token}"

            try:
                response = self.transport.request(
                    method,
                    path,
                    params=params,
                    json=json,
                    headers=request_headers,
                    timeout=timeout,
                )
            except requests.exceptions.Timeout as exc:
                raise TransportError(f"Request to {path} timed out") from exc
            except requests.exceptions.RequestException as exc:
                raise TransportError(f"Request to {path} failed: {exc}") from exc
            if self._should_retry(method, response.status_code, attempt):
                self._sleeper(self._retry_delay(response, attempt))
                continue
            if response.status_code == 401:
                self.credentials.invalidate()
            self._raise_for_status(response)
            return response.body

        raise AssertionError("retry loop exited without a response")

    def _should_retry(self, method: str, status_code: int, attempt: int) -> bool:
        return (
            method.upper() in {"GET", "HEAD", "OPTIONS"}
            and attempt < self.settings.max_retries
            and status_code in {429, 500, 502, 503, 504}
        )

    def _retry_delay(self, response: HttpResponse, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return float(self.settings.retry_delay * (2**attempt))

    @staticmethod
    def _raise_for_status(response: HttpResponse) -> None:
        if 200 <= response.status_code < 300:
            return

        message = CoreClient._message(response.body)
        kwargs: dict[str, Any] = {
            "status_code": response.status_code,
            "response": response.body if isinstance(response.body, dict) else None,
            "request_id": response.request_id,
        }
        if response.status_code == 401:
            raise AuthenticationError(message, **kwargs)
        if response.status_code == 403:
            raise ForbiddenError(message, **kwargs)
        if response.status_code == 404:
            raise NotFoundError(message, **kwargs)
        if response.status_code == 409:
            raise ConflictError(message, **kwargs)
        if response.status_code == 400:
            raise ValidationError(message, **kwargs)
        if response.status_code == 429:
            raise RateLimitError(message, **kwargs)
        if response.status_code >= 500:
            raise ServerError(message, **kwargs)
        raise MtnCloudError(message, **kwargs)

    @staticmethod
    def _message(body: Any) -> str:
        if isinstance(body, Mapping):
            for key in ("message", "error", "error_description", "msg"):
                value = body.get(key)
                if value:
                    return str(value)
        if isinstance(body, str) and body:
            return body
        return "MTN Cloud API request failed"

    def close(self) -> None:
        self.transport.close()
