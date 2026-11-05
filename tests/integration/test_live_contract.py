"""Opt-in live contract tests.

Run read-only checks with ``MTN_CLOUD_RUN_LIVE_TESTS=1``. The mutation test
also requires ``MTN_CLOUD_ALLOW_MUTATIONS=1`` and always attempts cleanup.
"""

from __future__ import annotations

import os
import time

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


@pytest.fixture(scope="module")
def live_client() -> MtnCloudClient:
    if not _enabled("MTN_CLOUD_RUN_LIVE_TESTS"):
        pytest.skip("set MTN_CLOUD_RUN_LIVE_TESTS=1 to run live tests")
    client = MtnCloudClient(settings=ClientSettings(timeout=30, max_retries=1))
    try:
        yield client
    finally:
        client.close()


def test_live_read_only_contract(live_client: MtnCloudClient) -> None:
    user = live_client.whoami()
    groups = live_client.groups.list(limit=20)
    instance_types = live_client.instance_types.list(limit=20)

    assert user.id is not None
    assert groups
    assert instance_types

    group = groups[0]
    assert group.cloud_ids
    pools = live_client.resource_pools.list(
        zone_id=group.cloud_ids[0],
        group_id=group.id,
    )
    assert pools

    networks = live_client.networks.list(zone_id=group.cloud_ids[0], limit=100)
    assert networks

    routers = live_client.routers.list(
        zone_id=group.cloud_ids[0],
        group_id=group.id,
        limit=20,
    )
    router_types = live_client.routers.list_types()
    network_types = live_client.networks.list_types()
    assert router_types
    assert network_types
    assert all(router.id > 0 for router in routers)

    subnets = live_client.networks.list_subnets(networks[0].id)
    assert all(subnet.network_id in (None, networks[0].id) for subnet in subnets)

    applications = live_client.apps.list(limit=20)
    assert all(application.id > 0 for application in applications)


def test_live_provisioning_dry_run(live_client: MtnCloudClient) -> None:
    group = live_client.groups.list(limit=1)[0]
    instance_type = live_client.instance_types.list(limit=1)[0]
    zone_id = group.cloud_ids[0]
    pools = live_client.resource_pools.list(zone_id=zone_id, group_id=group.id)
    pool = pools[0]
    plans = live_client.plans.list_for_provisioning(
        zone_id=zone_id,
        layout_id=instance_type.default_layout_id,
        group_id=group.id,
        resource_pool_id=pool.code,
    )
    plan = plans[0]

    resolved = live_client.instances.provision(
        f"sdk-dry-run-{int(time.time())}",
        type_code=instance_type.code,
        group=group.name or group.id,
        plan=plan.name or plan.id,
        resource_pool=pool.code,
        dry_run=True,
    )

    assert resolved["group_id"] == group.id
    assert resolved["zone_id"] == zone_id
    assert resolved["resource_pool_id"] == pool.code


@pytest.mark.mutation
def test_live_create_wait_delete(live_client: MtnCloudClient) -> None:
    """Provision one small VM from explicit selectors, wait for it, then delete it.

    Never picks the "first" group, type, pool or plan: those can belong to other
    projects or be unsuitable appliances. A dry run validates the selection
    before anything is created.
    """
    if not _enabled("MTN_CLOUD_ALLOW_MUTATIONS"):
        pytest.skip("set MTN_CLOUD_ALLOW_MUTATIONS=1 to run mutation tests")

    ids: dict[str, int] = {}
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

    options = {
        "type_code": type_code,
        "root_volume_size_gb": 10,
        **ids,
    }
    name = f"sdk-live-contract-{int(time.time())}"
    live_client.instances.provision(name, dry_run=True, **options)

    instance = None
    try:
        instance = live_client.instances.provision(name, wait=False, **options)
        instance = live_client.instances.wait_until_running(
            instance.id,
            timeout=1800,
            poll_interval=15,
        )
        assert instance.is_running
    finally:
        if instance is not None:
            live_client.instances.delete(instance.id, force=True)
            live_client.instances.wait_until_deleted(
                instance.id,
                timeout=600,
                poll_interval=15,
            )
        else:
            matches = [i for i in live_client.instances.list(name=name) if i.name == name]
            for orphan in matches:
                live_client.instances.delete(orphan.id, force=True)
                live_client.instances.wait_until_deleted(orphan.id, timeout=600, poll_interval=15)


def test_live_cli_inventory(
    live_client: MtnCloudClient, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from mtn_cloud.cli import main

    code = main(["inventory", "-o", "json"])
    assert code in {0, 3}
    document = json.loads(capsys.readouterr().out)

    assert document["schema"] == "mtncloud.inventory/v1"
