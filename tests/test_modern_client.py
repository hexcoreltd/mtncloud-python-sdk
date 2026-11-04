from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.instance import InstanceCreate, InstanceUpdate
from mtn_cloud.models.security_group import SecurityGroupCreate, SecurityGroupRuleCreate
from mtn_cloud.models.router import RouterCreate
from mtn_cloud.models.network import NetworkCreate, NetworkUpdate
from mtn_cloud.models.snapshot import SnapshotCreate
from mtn_cloud.modern_exceptions import TimeoutError as ModernTimeoutError
from mtn_cloud.modern_exceptions import AuthenticationError
from mtn_cloud.transport import HttpResponse


def test_settings_default_to_mtn_cloud_control_plane() -> None:
    settings = ClientSettings()

    assert settings.base_url == "https://console.cloud.mtn.ng"
    assert settings.api_url == "https://console.cloud.mtn.ng/api"


def test_settings_normalize_urls() -> None:
    settings = ClientSettings(base_url="https://example.test/", api_prefix="v2/")

    assert settings.api_url == "https://example.test/v2"


def test_whoami_uses_bearer_auth_and_parses_user() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        status_code=200,
        headers={},
        body={"user": {"id": 1, "username": "hakeem"}},
    )
    client = MtnCloudClient(token="secret", transport=transport)

    user = client.whoami()

    assert user.username == "hakeem"
    transport.request.assert_called_once_with(
        "GET",
        "/whoami",
        params=None,
        json=None,
        headers={"Authorization": "Bearer secret"},
        timeout=None,
    )


def test_http_errors_preserve_request_id() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        status_code=401,
        headers={},
        body={"message": "invalid token"},
        request_id="req-123",
    )
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(AuthenticationError) as raised:
        client.whoami()

    assert raised.value.request_id == "req-123"
    assert raised.value.status_code == 401


def test_get_retries_transient_responses_with_exponential_delay() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(503, {}, {"message": "busy"}),
        HttpResponse(200, {}, {"user": {"id": 1, "username": "hakeem"}}),
    ]
    sleeper = Mock()
    client = MtnCloudClient(
        settings=ClientSettings(
            token="secret",
            max_retries=2,
            retry_delay=0.25,
        ),
        transport=transport,
        sleeper=sleeper,
    )

    assert client.whoami().username == "hakeem"
    sleeper.assert_called_once_with(0.25)
    assert transport.request.call_count == 2


def test_mutating_requests_are_not_automatically_retried() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(503, {}, {"message": "busy"})
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(Exception):
        client._core.request("POST", "/instances", json={"name": "demo"})

    transport.request.assert_called_once()


def test_zones_service_parses_typed_pages() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "zones": [{"id": 1, "name": "MTNNG_CLOUD_AZ_1", "cloudType": "openstack"}],
            "meta": {"offset": 0, "max": 25, "total": 1},
        },
    )
    client = MtnCloudClient(token="secret", transport=transport)

    page = client.zones.list_page(limit=25, type_code="openstack")

    assert page.items[0].name == "MTNNG_CLOUD_AZ_1"
    assert page.total == 1
    assert page.has_more is False
    assert transport.request.call_args.kwargs["params"] == {"max": 25, "offset": 0, "type": "openstack"}


def test_groups_service_gets_wrapped_resource() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {"group": {"id": 7, "name": "project-a", "active": True}},
    )
    client = MtnCloudClient(token="secret", transport=transport)

    group = client.groups.get(7)

    assert group.id == 7
    assert group.name == "project-a"


def test_instance_types_service_parses_layouts() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "instanceTypes": [
                {
                    "id": 10,
                    "name": "Ubuntu 22.04",
                    "code": "ubuntu-2204",
                    "instanceTypeLayouts": [{"id": 20, "name": "Ubuntu layout"}],
                }
            ],
            "meta": {"total": 1},
        },
    )
    client = MtnCloudClient(token="secret", transport=transport)

    instance_type = client.instance_types.get_by_code("ubuntu-2204")

    assert instance_type.default_layout_id == 20
    assert instance_type.layouts[0].name == "Ubuntu layout"


def test_plans_service_parses_resource_sizes() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "servicePlans": [
                {"id": 30, "name": "small", "maxCores": 2, "maxMemory": 4294967296}
            ]
        },
    )
    client = MtnCloudClient(token="secret", transport=transport)

    plan = client.plans.get_by_name("small")

    assert plan.cores == 2
    assert plan.memory_gb == 4


def test_resource_pools_filter_non_selectable_group_rows() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "data": [
                {"isGroup": True, "name": "OpenStack"},
                {"id": 214, "value": "pool-214", "name": "project-a", "isDefault": True},
            ]
        },
    )
    client = MtnCloudClient(token="secret", transport=transport)

    pools = client.resource_pools.list(zone_id=4, group_id=621)

    assert len(pools) == 1
    assert pools[0].code == "pool-214"
    assert pools[0].is_default is True
    assert transport.request.call_args.kwargs["params"] == {
        "cloudId": 4,
        "groupId": 621,
        "provisionTypeCode": "openstack",
    }


def test_instances_service_lists_typed_instances() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {"instances": [{"id": 99, "name": "web-01", "status": "running"}]},
    )
    client = MtnCloudClient(token="secret", transport=transport)

    instances = client.instances.list(status="running")

    assert instances[0].id == 99
    assert instances[0].is_running is True
    assert transport.request.call_args.kwargs["params"] == {
        "offset": 0,
        "status": "running",
    }


def test_instances_service_create_serializes_request_model() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        201,
        {},
        {"instance": {"id": 100, "name": "web-01", "status": "provisioning"}},
    )
    client = MtnCloudClient(token="secret", transport=transport)
    request = InstanceCreate(
        name="web-01",
        cloud="MTNNG_CLOUD_AZ_1",
        type="ubuntu-2204",
        group_id=621,
        layout=20,
        plan=30,
        resource_pool_id="pool-214",
    )

    instance = client.instances.create(request)

    assert instance.id == 100
    assert transport.request.call_args.kwargs["json"]["instance"]["site"] == {"id": 621}


def test_instances_service_update_uses_put() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {"instance": {"id": 100, "name": "web-renamed", "status": "stopped"}},
    )
    client = MtnCloudClient(token="secret", transport=transport)

    instance = client.instances.update(100, InstanceUpdate(name="web-renamed"))

    assert instance.name == "web-renamed"
    assert transport.request.call_args.args[:2] == ("PUT", "/instances/100")


def test_instances_service_action_refreshes_instance() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(202, {}, {}),
        HttpResponse(200, {}, {"instance": {"id": 100, "status": "running"}}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    instance = client.instances.start(100)

    assert instance.is_running is True
    assert transport.request.call_args_list[0].args[:2] == ("PUT", "/instances/100/start")
    assert transport.request.call_args_list[1].args[:2] == ("GET", "/instances/100")


def test_instances_service_waiter_uses_monotonic_deadline() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {"instance": {"id": 100, "status": "provisioning"}}),
        HttpResponse(200, {}, {"instance": {"id": 100, "status": "running"}}),
    ]
    clock_values = iter([0.0, 1.0, 2.0])
    sleeper = Mock()
    client = MtnCloudClient(
        token="secret",
        transport=transport,
        sleeper=sleeper,
        clock=lambda: next(clock_values),
    )

    instance = client.instances.wait_until_running(100, timeout=10, poll_interval=5)

    assert instance.status == "running"
    sleeper.assert_called_once_with(5)


def test_instances_service_waiter_raises_typed_timeout() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {"instance": {"id": 100, "status": "provisioning"}},
    )
    clock_values = iter([0.0, 2.0])
    client = MtnCloudClient(
        token="secret",
        transport=transport,
        sleeper=Mock(),
        clock=lambda: next(clock_values),
    )

    with pytest.raises(ModernTimeoutError) as raised:
        client.instances.wait_until_running(100, timeout=1, poll_interval=5)

    assert raised.value.timeout == 1


def test_instance_provision_dry_run_resolves_dependencies() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {"groups": [{"id": 621, "name": "project-a", "zones": [{"id": 4, "name": "MTNNG_CLOUD_AZ_1"}]}]}),
        HttpResponse(200, {}, {"instanceTypes": [{"id": 10, "name": "Ubuntu", "code": "ubuntu", "instanceTypeLayouts": [{"id": 20, "name": "default"}]}]}),
        HttpResponse(200, {}, {"data": [{"id": 214, "value": "pool-214", "name": "project-a"}]}),
        HttpResponse(200, {}, {"plans": [{"id": 30, "name": "small"}]}),
        HttpResponse(200, {}, {"network": {"id": 50, "zone": {"id": 4}, "group": {"id": 621}, "zonePool": {"id": 214}}}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    resolved = client.instances.provision(
        "web-01",
        type_code="ubuntu",
        group="project-a",
        plan="small",
        dry_run=True,
        network_id=50,
        external_network_id="public-network-01",
    )

    assert resolved == {
        "name": "web-01",
        "cloud": "MTNNG_CLOUD_AZ_1",
        "group_id": 621,
        "zone_id": 4,
        "type": "ubuntu",
        "layout": 20,
        "plan": 30,
        "resource_pool_id": "pool-214",
        "external_network_id": "public-network-01",
    }


def test_networks_service_lists_networks_and_subnets() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {"networks": [{"id": 50, "name": "ubuntu_net", "cidr": "10.0.0.0/24"}]}),
        HttpResponse(200, {}, {"subnets": [{"id": 51, "cidr": "10.0.0.0/24"}]}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    network = client.networks.list(zone_id=4)[0]
    subnets = client.networks.list_subnets(network.id)

    assert network.name == "ubuntu_net"
    assert subnets[0].id == 51


def test_networks_service_discovers_types_and_ip_pools() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {"networkTypes": [{"id": 4, "code": "openstackPrivate", "category": "OpenStack"}]}),
        HttpResponse(200, {}, {"networkPools": [{"id": 8, "name": "private-pool", "ipCount": 10}]}),
        HttpResponse(200, {}, {"networkPoolIps": [{"id": 9, "ipAddress": "10.0.0.10"}]}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    network_type = client.networks.list_types(openstack_only=True)[0]
    pool = client.networks.list_pools()[0]
    pool_ip = client.networks.list_pool_ips(pool.id)[0]

    assert network_type.is_openstack is True
    assert pool.name == "private-pool"
    assert pool_ip.ip_address == "10.0.0.10"


def test_networks_service_creates_updates_and_deletes_networks() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(201, {}, {"network": {"id": 60, "name": "sdk-net", "cidr": "10.20.0.0/24"}}),
        HttpResponse(200, {}, {"network": {"id": 60, "name": "sdk-net-renamed"}}),
        HttpResponse(204, {}, None),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    network = client.networks.create(
        NetworkCreate(
            name="sdk-net",
            cloud_id=4,
            group_id=621,
            type_id=10,
            resource_pool_id=214,
            cidr="10.20.0.0/24",
        )
    )
    renamed = client.networks.update(60, NetworkUpdate(display_name="sdk-net-renamed"))
    assert client.networks.delete(60) is True

    assert network.id == 60
    assert renamed.name == "sdk-net-renamed"
    assert transport.request.call_args_list[0].kwargs["json"] == {
        "network": {
            "name": "sdk-net",
            "site": {"id": 621},
            "zone": {"id": 4},
            "type": {"id": 10},
            "zonePool": {"id": 214},
            "cidr": "10.20.0.0/24",
        }
    }


def test_routers_service_lists_external_networks() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {"success": True, "data": [{"value": 77, "name": "public-gateway"}]},
    )
    client = MtnCloudClient(token="secret", transport=transport)

    external = client.routers.list_external_networks(
        zone_id=4,
        group_id=621,
        resource_pool_code="pool-214",
        router_type_id=55,
    )[0]

    assert external.id == 77
    assert external.name == "public-gateway"
    assert transport.request.call_args.kwargs["params"] == {
        "router.zone.id": 4,
        "router.site.id": 621,
        "router.poolId": "pool-214",
        "routerType.id": 55,
    }


def test_routers_service_creates_and_reads_router() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {"success": True, "id": 99}),
        HttpResponse(
            200,
            {},
            {
                "networkRouter": {
                    "id": 99,
                    "name": "edge-router",
                    "status": "ok",
                    "type": {"id": 55, "code": "neutronRouter"},
                }
            },
        ),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    router = client.routers.create(
        RouterCreate(
            name="edge-router",
            group_id=621,
            cloud_id=4,
            resource_pool_id=214,
            internal_subnet_ids=[51],
        ),
        router_type_id=55,
    )

    assert router.id == 99
    assert router.status == "ok"
    assert transport.request.call_args_list[0].args[:2] == ("POST", "/networks/routers")
    assert transport.request.call_args_list[0].kwargs["json"]["networkRouter"]["poolId"] == "pool-214"


def test_instances_service_manages_snapshots() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {"snapshots": [{"id": 80, "name": "before-upgrade"}]}),
        HttpResponse(201, {}, {"snapshot": {"id": 81, "name": "after-upgrade"}}),
        HttpResponse(202, {}, {}),
        HttpResponse(204, {}, None),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    snapshots = client.instances.list_snapshots(100)
    created = client.instances.create_snapshot(100, SnapshotCreate(name="after-upgrade"))
    assert client.instances.revert_snapshot(100, 81) is True
    assert client.instances.delete_snapshot(100, 81) is True

    assert snapshots[0].id == 80
    assert created.name == "after-upgrade"
    assert transport.request.call_args_list[1].kwargs["json"] == {
        "snapshot": {"name": "after-upgrade"}
    }


def test_backups_service_lists_and_executes_backups() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {"backups": [{"id": 90, "name": "nightly", "status": "active"}]}),
        HttpResponse(200, {}, {"results": [{"id": 91, "backupId": 90, "status": "success"}]}),
        HttpResponse(202, {}, {"success": True}),
        HttpResponse(200, {}, {"jobs": [{"id": 92, "name": "nightly-job"}]}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    backup = client.backups.list()[0]
    result = client.backups.list_results(backup.id)[0]
    execution = client.backups.execute(backup.id)
    job = client.backups.list_jobs()[0]

    assert backup.name == "nightly"
    assert result.status == "success"
    assert execution["success"] is True
    assert job.id == 92


def test_volumes_service_discovers_and_filters_attached_volumes() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(
            200,
            {},
            {
                "storageVolumes": [
                    {"id": 9450, "name": "root", "maxStorage": 42949672960, "instanceId": 4737}
                ],
                "meta": {"offset": 0, "max": 10, "total": 1},
            },
        ),
        HttpResponse(200, {}, {"storageVolume": {"id": 9450, "name": "root", "status": "provisioned"}}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    attached = client.volumes.list_attached(4737)
    volume = client.volumes.get(9450)

    assert attached[0].is_attached is True
    assert volume.status == "provisioned"
    assert transport.request.call_args_list[0].kwargs["params"] == {
        "offset": 0,
        "instanceId": 4737,
    }


def test_volumes_service_discovers_enabled_volume_types() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "storageVolumeTypes": [
                {"id": 11, "code": "openstackVolume", "name": "OpenStack Volume", "enabled": True},
                {"id": 12, "code": "disabled", "name": "Disabled", "enabled": False},
            ]
        },
    )
    client = MtnCloudClient(token="secret", transport=transport)

    types = client.volumes.list_types()

    assert [item.code for item in types] == ["openstackVolume"]
    assert transport.request.call_args.kwargs["params"] == {
        "offset": 0,
        "category": "volume",
    }


def test_security_groups_service_manages_groups_and_rules() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(201, {}, {"securityGroup": {"id": 70, "name": "sdk-test"}}),
        HttpResponse(201, {}, {"rule": {"id": 71, "name": "allow-ssh", "direction": "ingress"}}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    group = client.security_groups.create(SecurityGroupCreate(name="sdk-test"))
    rule = client.security_groups.create_rule(
        group.id,
        SecurityGroupRuleCreate(name="allow-ssh", protocol="tcp", port_range="22"),
    )

    assert group.id == 70
    assert rule.id == 71
    assert transport.request.call_args_list[1].args[:2] == (
        "POST",
        "/security-groups/70/rules",
    )
