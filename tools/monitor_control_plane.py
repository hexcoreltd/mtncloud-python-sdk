"""Standalone, unauthenticated HTTP availability monitor (requires requests only)."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from urllib.parse import urlsplit

import requests
from requests.auth import AuthBase

DEFAULT_URL = "https://console.cloud.mtn.ng/ping"


class NoCredentials(AuthBase):
    """Suppress automatic netrc authentication while preserving proxy/CA settings."""

    def __call__(self, request: requests.PreparedRequest) -> requests.PreparedRequest:
        request.headers.pop("Authorization", None)
        return request


def validate_url(value: str) -> str:
    """Reject credential-bearing or malformed targets without echoing them."""
    try:
        parts = urlsplit(value)
        port = parts.port
        valid = (
            parts.scheme in {"http", "https"}
            and bool(parts.hostname)
            and parts.username is None
            and parts.password is None
            and not parts.query
            and not parts.fragment
            and (port is None or 1 <= port <= 65535)
            and not any(character.isspace() or ord(character) < 32 for character in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("URL must be HTTP(S), without credentials, query strings or fragments")
    return value


def positive_seconds(value: float) -> float:
    if not isfinite(value) or value <= 0:
        raise ValueError("Time values must be finite and positive")
    return value


@dataclass(frozen=True)
class ProbeResult:
    timestamp: str
    url: str
    status_code: int | None
    latency_ms: float
    healthy: bool
    error: str | None = None
    message: str | None = None


def probe(
    url: str = DEFAULT_URL, *, connect_timeout: float = 5, read_timeout: float = 15
) -> ProbeResult:
    """Measure one GET through response headers; do not read the response body."""
    validate_url(url)
    positive_seconds(connect_timeout)
    positive_seconds(read_timeout)
    timestamp = datetime.now(timezone.utc).isoformat()
    status_code = None
    error = message = None
    start = time.perf_counter()
    try:
        # A fresh session avoids carrying cookies between checks. No SDK client,
        # environment token or .env file participates in this request.
        with requests.Session() as session:
            with session.get(
                url,
                auth=NoCredentials(),
                timeout=(connect_timeout, read_timeout),
                allow_redirects=False,
                stream=True,
            ) as response:
                status_code = response.status_code
                if not 200 <= status_code < 300:
                    error = "HTTPStatusError"
                    message = "Endpoint returned a status outside HTTP 200-299."
    except requests.RequestException as exc:
        error = type(exc).__name__
        # Exception messages may include proxy credentials or internal URLs.
        message = "HTTP probe failed; inspect the error category and monitor network access."
    return ProbeResult(
        timestamp=timestamp,
        url=url,
        status_code=status_code,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
        healthy=status_code is not None and 200 <= status_code < 300 and error is None,
        error=error,
        message=message,
    )


@dataclass
class FailureTracker:
    threshold: int = 3
    consecutive_failures: int = 0
    alerting: bool = False

    def __post_init__(self) -> None:
        if self.threshold < 1:
            raise ValueError("Failure threshold must be at least 1")

    def observe(self, healthy: bool) -> str | None:
        """Emit one alert on reaching the threshold and one recovery afterwards."""
        if healthy:
            self.consecutive_failures = 0
            if self.alerting:
                self.alerting = False
                return "recovery"
        else:
            self.consecutive_failures += 1
            if not self.alerting and self.consecutive_failures >= self.threshold:
                self.alerting = True
                return "alert"
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--connect-timeout", type=float, default=5)
    parser.add_argument("--read-timeout", type=float, default=15)
    parser.add_argument("--watch", action="store_true", help="Repeat until interrupted.")
    parser.add_argument("--interval", type=float, default=60, help="Seconds between checks.")
    parser.add_argument("--failure-threshold", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        validate_url(args.url)
        for value in (args.connect_timeout, args.read_timeout, args.interval):
            positive_seconds(value)
        tracker = FailureTracker(threshold=args.failure_threshold)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        while True:
            result = probe(
                args.url, connect_timeout=args.connect_timeout, read_timeout=args.read_timeout
            )
            event = tracker.observe(result.healthy)
            print(
                json.dumps(
                    {
                        "schema": "mtncloud.availability/v1",
                        **asdict(result),
                        "consecutive_failures": tracker.consecutive_failures,
                        "alerting": tracker.alerting,
                        "event": event,
                    }
                ),
                flush=True,
            )
            if not args.watch:
                return 0 if result.healthy else 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
