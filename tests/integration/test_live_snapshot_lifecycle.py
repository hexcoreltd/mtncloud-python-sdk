"""Guarded snapshot and process lifecycle against a throwaway instance.

Creates billable resources. Requires MTN_CLOUD_RUN_LIVE_TESTS=1,
MTN_CLOUD_ALLOW_MUTATIONS=1 and the MTN_CLOUD_TEST_* selectors used by the
instance lifecycle test. It never touches an existing instance: it provisions
its own, snapshots it, tracks the submission processes, restores the snapshot,
deletes it and finally deletes the instance.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.snapshot import SnapshotCreate


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


@pytest.fixture
def mutation_client() -> Iterator[MtnCloudClient]:
    if not _enabled("MTN_CLOUD_RUN_LIVE_TESTS"):
        pytest.skip("set MTN_CLOUD_RUN_LIVE_TESTS=1 to run live tests")
    if not _enabled("MTN_CLOUD_ALLOW_MUTATIONS"):
        pytest.skip("set MTN_CLOUD_ALLOW_MUTATIONS=1 to run mutation tests")
    with MtnCloudClient(settings=ClientSettings(timeout=60, max_retries=2)) as client:
        yield client


def _selectors() -> dict[str, object]:
    ids: dict[str, object] = {}
    for field, variable in {
        "group": "MTN_CLOUD_TEST_GROUP_ID",
        "zone": "MTN_CLOUD_TEST_ZONE_ID",
        "resource_pool": "MTN_CLOUD_TEST_POOL_ID",
        "plan": "MTN_CLOUD_TEST_PLAN_ID",
        "layout": "MTN_CLOUD_TEST_LAYOUT_ID",
        "network_id": "MTN_CLOUD_TEST_NETWORK_ID",
    }.items():
        raw = os.getenv(variable, "")
        if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
            pytest.fail(f"Set {variable} to a positive test resource ID before mutation")
        ids[field] = int(raw)
    type_code = os.getenv("MTN_CLOUD_TEST_INSTANCE_TYPE_CODE", "").strip()
    if not type_code:
        pytest.fail("Set MTN_CLOUD_TEST_INSTANCE_TYPE_CODE before mutation")
    return {"type_code": type_code, "root_volume_size_gb": 10, **ids}


def _poll(check: Callable[[], bool], *, timeout: float, interval: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() >= deadline:
            pytest.fail(f"Timed out waiting for {what}", pytrace=False)
        time.sleep(interval)


@pytest.mark.mutation
def test_live_snapshot_process_restore_delete(mutation_client: MtnCloudClient) -> None:
    client = mutation_client
    options = _selectors()
    tag = uuid4().hex[:10]
    instance_name = f"sdk-snapshot-host-{tag}"
    snapshot_name = f"sdk-snapshot-{tag}"
    client.instances.provision(instance_name, dry_run=True, **options)

    instance_id: int | None = None
    try:
        instance = client.instances.provision(instance_name, wait=False, **options)
        instance_id = instance.id
        client.instances.wait_until_running(instance_id, timeout=1800, poll_interval=15)

        submission = client.instances.create_snapshot(
            instance_id, SnapshotCreate(name=snapshot_name)
        )
        assert submission.instance_id == instance_id
        for process_id in submission.process_ids:
            process = client.processes.wait_for_status(
                process_id,
                "complete",
                instance_id=instance_id,
                failure_statuses={"failed"},
                timeout=1800,
                poll_interval=15,
            )
            assert process.id == process_id

        def snapshot_listed() -> bool:
            return any(
                s.name == snapshot_name for s in client.instances.list_snapshots(instance_id)
            )

        _poll(snapshot_listed, timeout=900, interval=15, what="the snapshot to be listed")
        snapshot = client.instances.get_snapshot_by_name(instance_id, snapshot_name)
        assert client.snapshots.get(snapshot.id).id == snapshot.id

        assert client.instances.revert_snapshot(instance_id, snapshot.id) is True
        client.instances.wait_until_running(instance_id, timeout=1800, poll_interval=15)

        assert client.instances.delete_snapshot(instance_id, snapshot.id) is True

        def snapshot_gone() -> bool:
            return all(s.id != snapshot.id for s in client.instances.list_snapshots(instance_id))

        _poll(snapshot_gone, timeout=900, interval=15, what="the snapshot to be deleted")
    finally:
        # Each step runs even if an earlier one fails; the first error is
        # re-raised. Names are unique per run, so every match belongs to this test.
        failures: list[BaseException] = []
        instance_ids = {instance_id} if instance_id is not None else set()
        try:
            instance_ids |= {
                i.id for i in client.instances.list(name=instance_name) if i.name == instance_name
            }
        except Exception as exc:
            failures.append(exc)
        for host_id in instance_ids:
            try:
                for leftover in client.instances.list_snapshots(host_id):
                    if leftover.name == snapshot_name:
                        client.snapshots.delete(leftover.id)
            except Exception as exc:
                failures.append(exc)
            try:
                client.instances.delete(host_id, force=True)
                client.instances.wait_until_deleted(host_id, timeout=600, poll_interval=15)
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise failures[0]
