"""Guarded existing snapshot reads; never create, revert or delete snapshots."""

import os

import pytest

from mtn_cloud import MtnCloudClient


@pytest.fixture
def instance_id() -> int:
    value = os.getenv("MTN_CLOUD_TEST_INSTANCE_ID")
    if not value:
        pytest.skip("Set MTN_CLOUD_TEST_INSTANCE_ID to inspect an existing instance's snapshots")
    if not value.isascii() or not value.isdigit() or int(value) <= 0:
        pytest.fail("MTN_CLOUD_TEST_INSTANCE_ID must be a positive numeric ID", pytrace=False)
    return int(value)


def test_live_snapshot_collection(instance_id: int, authenticated_client: MtnCloudClient) -> None:
    body = authenticated_client._core.request("GET", f"/instances/{instance_id}/snapshots")
    if not isinstance(body, dict) or not isinstance(body.get("snapshots"), list):
        pytest.fail("Expected a JSON snapshots collection envelope", pytrace=False)
    snapshots = authenticated_client.instances.list_snapshots(instance_id)
    assert all(item.id > 0 for item in snapshots)


def test_live_snapshot_detail(instance_id: int, authenticated_client: MtnCloudClient) -> None:
    snapshots = authenticated_client.instances.list_snapshots(instance_id)
    if not snapshots:
        pytest.skip("No snapshots available; global detail contract was not exercised")
    assert authenticated_client.snapshots.get(snapshots[0].id).id == snapshots[0].id


def test_live_snapshot_scoped_lookup(
    instance_id: int, authenticated_client: MtnCloudClient
) -> None:
    snapshots = authenticated_client.instances.list_snapshots(instance_id)
    if not snapshots:
        pytest.skip("No snapshots available; scoped lookup contract was not exercised")
    assert (
        authenticated_client.instances.get_snapshot(instance_id, snapshots[0].id).id
        == snapshots[0].id
    )


def test_live_snapshot_name_lookup(instance_id: int, authenticated_client: MtnCloudClient) -> None:
    name = os.getenv("MTN_CLOUD_TEST_SNAPSHOT_NAME")
    if not name:
        pytest.skip("Set MTN_CLOUD_TEST_SNAPSHOT_NAME to an existing unique snapshot name")
    assert authenticated_client.instances.get_snapshot_by_name(instance_id, name).name == name
