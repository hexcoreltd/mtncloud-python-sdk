"""Shared authenticated fixtures for opt-in live contract checks."""

import os
from collections.abc import Iterator

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.modern_exceptions import MtnCloudError


@pytest.fixture(scope="module")
def authenticated_client() -> Iterator[MtnCloudClient]:
    if os.getenv("MTN_CLOUD_RUN_LIVE_TESTS", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("set MTN_CLOUD_RUN_LIVE_TESTS=1 to run live contract tests")
    settings = ClientSettings(timeout=10, max_retries=0)
    if not settings.token_value():
        pytest.fail("Live contract tests require MTN Cloud credentials")
    with MtnCloudClient(settings=settings) as client:
        failure = None
        try:
            client.whoami()
        except MtnCloudError as exc:
            failure = (
                f"Authentication preflight failed: {type(exc).__name__}; status={exc.status_code}"
            )
        if failure is not None:
            pytest.fail(failure, pytrace=False)
        yield client


@pytest.fixture(scope="module")
def storage_client(authenticated_client: MtnCloudClient) -> MtnCloudClient:
    """Retain the storage fixture name for existing contract suites."""
    return authenticated_client
