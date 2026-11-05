"""Guarded process reads; no snapshot creation, process retry or cancellation."""

import os

import pytest

from mtn_cloud import MtnCloudClient


def optional_id(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    if not value.isascii() or not value.isdigit() or int(value) <= 0:
        pytest.fail(f"{name} must contain a positive numeric ID", pytrace=False)
    return int(value)


def test_live_process_history_envelope(authenticated_client: MtnCloudClient) -> None:
    body = authenticated_client._core.request("GET", "/processes")
    if not isinstance(body, dict) or not isinstance(body.get("processes"), list):
        pytest.fail("Expected a JSON processes collection envelope", pytrace=False)
    page = authenticated_client.processes.list_page()
    assert all(process.id > 0 for process in page.items)


def test_live_process_detail(authenticated_client: MtnCloudClient) -> None:
    process_id = optional_id("MTN_CLOUD_TEST_PROCESS_ID")
    if process_id is None:
        pytest.skip("Set MTN_CLOUD_TEST_PROCESS_ID to an existing readable process")
    instance_id = optional_id("MTN_CLOUD_TEST_INSTANCE_ID")
    process = authenticated_client.processes.get(process_id, instance_id=instance_id)
    assert process.id == process_id
    assert all(event.process_id in (None, process_id) for event in process.events)


def test_live_instance_process_filter(authenticated_client: MtnCloudClient) -> None:
    instance_id = optional_id("MTN_CLOUD_TEST_INSTANCE_ID")
    if instance_id is None:
        pytest.skip("Set MTN_CLOUD_TEST_INSTANCE_ID to check process history filtering")
    processes = authenticated_client.processes.list(instance_id=instance_id)
    if not processes:
        pytest.skip("No process data available; filtered item contract was not exercised")
    if any(process.instance_id is None for process in processes):
        pytest.skip("Missing instance references leave item ownership unverified")
    assert all(process.instance_id == instance_id for process in processes)
