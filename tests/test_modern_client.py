import copy
from typing import Any
from unittest.mock import Mock

import pytest
import requests

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.instance import InstanceCreate, InstanceUpdate
from mtn_cloud.models.network import NetworkCreate, NetworkUpdate
from mtn_cloud.models.router import RouterCreate
from mtn_cloud.models.security_group import SecurityGroupCreate, SecurityGroupRuleCreate
from mtn_cloud.models.snapshot import SnapshotCreate
from mtn_cloud.models.storage_bucket import StorageBucketCreate, StorageBucketUpdate
from mtn_cloud.modern_exceptions import (
    AmbiguousLookupError,
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    LookupNotFoundError,
    MtnCloudError,
    NotFoundError,
    ServerError,
    TransportError,
)
from mtn_cloud.modern_exceptions import TimeoutError as ModernTimeoutError
from mtn_cloud.services.instances import InstancesService
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

    with pytest.raises(MtnCloudError):
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
    assert transport.request.call_args.kwargs["params"] == {
        "max": 25,
        "offset": 0,
        "type": "openstack",
    }


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
        {"servicePlans": [{"id": 30, "name": "small", "maxCores": 2, "maxMemory": 4294967296}]},
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
        HttpResponse(
            200,
            {},
            {
                "groups": [
                    {
                        "id": 621,
                        "name": "project-a",
                        "zones": [{"id": 4, "name": "MTNNG_CLOUD_AZ_1"}],
                    }
                ]
            },
        ),
        HttpResponse(
            200,
            {},
            {
                "instanceTypes": [
                    {
                        "id": 10,
                        "name": "Ubuntu",
                        "code": "ubuntu",
                        "instanceTypeLayouts": [{"id": 20, "name": "default"}],
                    }
                ]
            },
        ),
        HttpResponse(200, {}, {"data": [{"id": 214, "value": "pool-214", "name": "project-a"}]}),
        HttpResponse(200, {}, {"plans": [{"id": 30, "name": "small"}]}),
        HttpResponse(
            200,
            {},
            {
                "network": {
                    "id": 50,
                    "zone": {"id": 4},
                    "group": {"id": 621},
                    "zonePool": {"id": 214},
                }
            },
        ),
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
        HttpResponse(
            200, {}, {"networks": [{"id": 50, "name": "ubuntu_net", "cidr": "10.0.0.0/24"}]}
        ),
        HttpResponse(200, {}, {"subnets": [{"id": 51, "cidr": "10.0.0.0/24"}]}),
        HttpResponse(200, {}, {"subnets": [{"id": 51, "cidr": "10.0.0.0/24"}]}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    network = client.networks.list(zone_id=4)[0]
    subnets = client.networks.list_subnets(network.id)

    assert network.name == "ubuntu_net"
    assert subnets[0].id == 51
    assert client.networks.get_subnet(50, 51).cidr == "10.0.0.0/24"


def test_networks_service_resolves_subnet_by_name() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {"subnets": [{"id": 51, "name": "private-subnet", "cidr": "10.0.0.0/24"}]},
    )
    client = MtnCloudClient(token="secret", transport=transport)

    subnet = client.networks.get_subnet_by_name(50, "private-subnet")

    assert subnet.id == 51
    assert transport.request.call_args.args[:2] == ("GET", "/networks/50/subnets")


def test_networks_service_rejects_unknown_subnet() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(200, {}, {"subnets": [{"id": 51}]})
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(ValueError, match="Subnet 99 was not found"):
        client.networks.get_subnet(50, 99)


def test_networks_service_discovers_types_and_ip_pools() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(
            200,
            {},
            {"networkTypes": [{"id": 4, "code": "openstackPrivate", "category": "OpenStack"}]},
        ),
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


def test_networks_service_resolves_pool_ip_by_address() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {"networkPoolIps": [{"id": 9, "ipAddress": "10.0.0.10", "active": True}]},
    )
    client = MtnCloudClient(token="secret", transport=transport)

    pool_ip = client.networks.get_pool_ip(8, "10.0.0.10")

    assert pool_ip.id == 9
    assert transport.request.call_args.kwargs["params"] == {"ipAddress": "10.0.0.10"}


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
    assert (
        transport.request.call_args_list[0].kwargs["json"]["networkRouter"]["poolId"] == "pool-214"
    )


def test_routers_service_lists_and_resolves_interfaces() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "networkRouter": {
                "id": 99,
                "name": "edge-router",
                "interfaces": [
                    {
                        "cidr": "10.0.0.0/24",
                        "networkSubnet": {"id": 4112, "name": "private-subnet"},
                    }
                ],
            }
        },
    )
    client = MtnCloudClient(token="secret", transport=transport)

    interface = client.routers.get_interface(99, 4112)

    assert interface.subnet_id == 4112
    assert interface.cidr == "10.0.0.0/24"
    assert transport.request.call_args.args[:2] == ("GET", "/networks/routers/99")


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
        HttpResponse(
            200, {}, {"storageVolume": {"id": 9450, "name": "root", "status": "provisioned"}}
        ),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    attached = client.volumes.list_attached(4737)
    volume = client.volumes.get(9450)

    assert attached[0].is_attached is True
    assert volume.status == "provisioned"
    assert transport.request.call_args_list[0].kwargs["params"] == {
        "max": 100,
        "offset": 0,
        "instanceId": 4737,
    }


def test_volumes_service_resolves_names_and_unattached_volumes() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(
            200,
            {},
            {
                "storageVolumes": [
                    {"id": 9450, "name": "root", "status": "provisioned"},
                    {"id": 9451, "name": "data", "status": "attached", "instanceId": 4737},
                ]
            },
        ),
        HttpResponse(
            200,
            {},
            {
                "storageVolumes": [
                    {"id": 9450, "name": "root", "status": "provisioned", "instanceId": None}
                ]
            },
        ),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    assert client.volumes.get_by_name("root").id == 9450
    unattached = client.volumes.list_unattached()

    assert [volume.name for volume in unattached] == ["root"]
    assert unattached[0].is_available is True


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


def test_storage_buckets_service_manages_s3_provider_configuration() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(
            201, {}, {"storageBucket": {"id": 110, "name": "backups", "providerType": "s3"}}
        ),
        HttpResponse(200, {}, {"storageBucket": {"id": 110, "name": "backups-renamed"}}),
        HttpResponse(204, {}, None),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    bucket = client.storage_buckets.create(
        StorageBucketCreate(
            name="backups",
            bucket_name="hexcore-backups",
            config={
                "accessKey": "access-key",
                "secretKey": "secret-key",
                "endpoint": "https://object-storage.example",
            },
            create_bucket=False,
        )
    )
    renamed = client.storage_buckets.update(110, StorageBucketUpdate(name="backups-renamed"))
    assert client.storage_buckets.delete(110) is True

    assert bucket.is_s3 is True
    assert renamed.name == "backups-renamed"
    assert (
        transport.request.call_args_list[0].kwargs["json"]["storageBucket"]["bucketName"]
        == "hexcore-backups"
    )
    assert transport.request.call_args_list[2].kwargs["params"] is None


def test_applications_service_discovers_catalog_deployments() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(
            200,
            {},
            {
                "apps": [
                    {"id": 120, "name": "managed-db", "status": "running", "type": "database"}
                ],
                "meta": {"offset": 0, "max": 10, "total": 1},
            },
        ),
        HttpResponse(200, {}, {"app": {"id": 120, "name": "managed-db", "status": "active"}}),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    application = client.apps.list(status="running")[0]
    fetched = client.apps.get(120)

    assert application.is_running is True
    assert fetched.status == "active"
    assert transport.request.call_args_list[0].kwargs["params"] == {
        "offset": 0,
        "status": "running",
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


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(403, ForbiddenError), (409, ConflictError)],
)
def test_http_errors_map_forbidden_and_conflict(
    status_code: int, error_type: type[MtnCloudError]
) -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        status_code, {}, {"message": "rejected"}, request_id="req-9"
    )
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(error_type) as raised:
        client.whoami()

    assert raised.value.status_code == status_code
    assert raised.value.request_id == "req-9"


def _lookup_cases() -> list[tuple[dict[str, Any], Any, str]]:
    return [
        ({"subnets": [{"id": 51}]}, lambda c: c.networks.get_subnet(50, 99), "Subnet 99"),
        (
            {"subnets": [{"id": 51, "name": "a"}]},
            lambda c: c.networks.get_subnet_by_name(50, "b"),
            "Subnet 'b'",
        ),
        (
            {"networkPoolIps": []},
            lambda c: c.networks.get_pool_ip(8, "10.0.0.10"),
            "IP address '10.0.0.10'",
        ),
        ({"storageVolumes": []}, lambda c: c.volumes.get_by_name("root"), "Storage volume"),
        (
            {"networkRouter": {"id": 5, "name": "edge-router", "interfaces": []}},
            lambda c: c.routers.get_interface(5, 51),
            "no interface for subnet 51",
        ),
    ]


@pytest.mark.parametrize(("body", "lookup", "message"), _lookup_cases())
def test_client_side_lookups_raise_not_found(
    body: dict[str, Any], lookup: Any, message: str
) -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(200, {}, body)
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(LookupNotFoundError, match=message) as raised:
        lookup(client)

    assert isinstance(raised.value, NotFoundError)
    # Kept catchable as ValueError for callers written against earlier releases.
    assert isinstance(raised.value, ValueError)


def _ambiguous_cases() -> list[tuple[dict[str, Any], Any]]:
    interface = {"networkSubnet": {"id": 51}}
    return [
        (
            {"subnets": [{"id": 51, "name": "a"}, {"id": 52, "name": "a"}]},
            lambda c: c.networks.get_subnet_by_name(50, "a"),
        ),
        (
            {"networkPoolIps": [{"id": 1, "ipAddress": "10.0.0.10"}] * 2},
            lambda c: c.networks.get_pool_ip(8, "10.0.0.10"),
        ),
        (
            {"storageVolumes": [{"id": 1, "name": "root"}, {"id": 2, "name": "root"}]},
            lambda c: c.volumes.get_by_name("root"),
        ),
        (
            {"networkRouter": {"id": 5, "name": "r", "interfaces": [interface, interface]}},
            lambda c: c.routers.get_interface(5, 51),
        ),
    ]


@pytest.mark.parametrize(("body", "lookup"), _ambiguous_cases())
def test_ambiguous_lookups_raise_value_error_not_not_found(
    body: dict[str, Any], lookup: Any
) -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(200, {}, body)
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(ValueError) as raised:
        lookup(client)

    assert not isinstance(raised.value, NotFoundError)


def test_provisioning_rejects_unknown_layout_name_as_not_found() -> None:
    instance_type = Mock(code="MTN-CS10")
    instance_type.get_layout_by_name.return_value = None

    with pytest.raises(LookupNotFoundError, match="Layout 'missing' not found"):
        InstancesService._resolve_layout(instance_type, "missing")


def test_http_errors_carry_operation_metadata() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        404, {}, {"message": "missing"}, request_id="req-404"
    )
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(NotFoundError) as raised:
        client.instances.get(5)

    error = raised.value
    assert (error.method, error.path, error.attempts) == ("GET", "/instances/5", 1)
    assert str(error) == "missing (HTTP 404) [GET /instances/5, request_id=req-404]"


def test_retried_errors_report_attempt_count() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(503, {}, {"message": "busy"})
    client = MtnCloudClient(
        settings=ClientSettings(token="secret", max_retries=2, retry_delay=0),
        transport=transport,
        sleeper=Mock(),
    )

    with pytest.raises(ServerError) as raised:
        client.whoami()

    assert raised.value.attempts == 3
    assert str(raised.value) == "busy (HTTP 503) [GET /whoami, attempts=3]"


def test_transport_errors_carry_operation_metadata() -> None:
    transport = Mock()
    transport.request.side_effect = requests.exceptions.ConnectTimeout("slow")
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(TransportError) as raised:
        client._core.request("post", "/instances", json={"name": "demo"})

    error = raised.value
    assert (error.method, error.path, error.attempts) == ("POST", "/instances", 1)
    assert error.status_code is None
    assert str(error).endswith("[POST /instances]")


def test_error_metadata_never_includes_query_string_or_credentials() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(400, {}, {"message": "bad"})
    client = MtnCloudClient(token="secret-token", transport=transport)

    with pytest.raises(MtnCloudError) as raised:
        client._core.request("GET", "/instances?name=private", params={"phrase": "private"})

    assert raised.value.path == "/instances"
    assert "private" not in str(raised.value)
    assert "secret-token" not in str(raised.value)


def test_error_format_is_unchanged_without_operation_metadata() -> None:
    error = MtnCloudError("failed", status_code=500, request_id="req-1")

    assert (error.method, error.path, error.attempts) == (None, None, None)
    assert str(error) == "failed (HTTP 500) [request_id=req-1]"


def test_connection_errors_do_not_leak_urls_into_messages() -> None:
    transport = Mock()
    cause = requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='console.cloud.mtn.ng'): url: /api/instances?name=private"
    )
    transport.request.side_effect = cause
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(TransportError) as raised:
        client._core.request("GET", "/instances", params={"name": "private"})

    assert "private" not in str(raised.value)
    assert str(raised.value) == "Request to /instances failed: ConnectionError [GET /instances]"
    # The original exception stays attached for debugging.
    assert raised.value.__cause__ is cause


def test_transport_error_after_retry_reports_attempt_count() -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(503, {}, {"message": "busy"}),
        requests.exceptions.ConnectionError("reset"),
    ]
    client = MtnCloudClient(
        settings=ClientSettings(token="secret", max_retries=2, retry_delay=0),
        transport=transport,
        sleeper=Mock(),
    )

    with pytest.raises(TransportError) as raised:
        client.whoami()

    assert raised.value.attempts == 2


def test_authentication_errors_normalize_method_and_carry_metadata() -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(401, {}, {"message": "invalid token"})
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(AuthenticationError) as raised:
        client._core.request("delete", "/instances/5")

    assert (raised.value.method, raised.value.path, raised.value.attempts) == (
        "DELETE",
        "/instances/5",
        1,
    )


def _modern_error_classes() -> list[type[MtnCloudError]]:
    import inspect

    from mtn_cloud import modern_exceptions

    return [
        cls
        for _, cls in inspect.getmembers(modern_exceptions, inspect.isclass)
        if issubclass(cls, MtnCloudError)
    ]


@pytest.mark.parametrize("error_type", _modern_error_classes(), ids=lambda cls: cls.__name__)
def test_modern_errors_survive_pickling(error_type: type[MtnCloudError]) -> None:
    import pickle

    extra: dict[str, Any] = {"timeout": 30.0} if error_type is ModernTimeoutError else {}
    error = error_type(
        "failed",
        status_code=503,
        response={"message": "failed"},
        request_id="req-1",
        method="GET",
        path="/whoami",
        attempts=2,
        **extra,
    )

    restored = pickle.loads(pickle.dumps(error))

    assert type(restored) is error_type
    assert restored.__dict__ == error.__dict__
    assert restored.args == error.args
    assert str(restored) == str(error)

    copied = copy.deepcopy(error)
    assert type(copied) is error_type
    assert copied.__dict__ == error.__dict__
    assert copied.response is not error.response


def _instances_response(ids: list[int], **meta: Any) -> HttpResponse:
    body: dict[str, Any] = {"instances": [{"id": item} for item in ids]}
    if meta:
        body["meta"] = meta
    return HttpResponse(200, {}, body)


def test_list_all_follows_pages_until_total() -> None:
    transport = Mock()
    transport.request.side_effect = [
        _instances_response([1, 2], total=3),
        _instances_response([3], total=3),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    instances = client.instances.list_all(page_size=2)

    assert [item.id for item in instances] == [1, 2, 3]
    assert transport.request.call_count == 2
    second_params = transport.request.call_args_list[1].kwargs["params"]
    assert second_params["offset"] == 2
    assert second_params["max"] == 2


def test_list_all_stops_on_short_page_without_total() -> None:
    transport = Mock()
    transport.request.return_value = _instances_response([1])
    client = MtnCloudClient(token="secret", transport=transport)

    instances = client.instances.list_all(page_size=2)

    assert [item.id for item in instances] == [1]
    assert transport.request.call_count == 1


def test_list_all_stops_on_empty_page() -> None:
    transport = Mock()
    transport.request.return_value = _instances_response([], total=10)
    client = MtnCloudClient(token="secret", transport=transport)

    assert client.instances.list_all(page_size=2) == []
    assert transport.request.call_count == 1


def test_list_all_rejects_provider_ignoring_offset() -> None:
    transport = Mock()
    transport.request.return_value = _instances_response([1, 2], offset=0, total=4)
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(MtnCloudError, match="unexpected offset"):
        client.instances.list_all(page_size=2)
    assert transport.request.call_count == 2


def test_list_all_passes_filters_to_every_page() -> None:
    transport = Mock()
    transport.request.side_effect = [
        _instances_response([1, 2], total=3),
        _instances_response([3], total=3),
    ]
    client = MtnCloudClient(token="secret", transport=transport)

    client.instances.list_all(page_size=2, zone_id=4)

    for call in transport.request.call_args_list:
        assert call.kwargs["params"]["zoneId"] == 4


def test_list_all_propagates_mid_pagination_errors() -> None:
    transport = Mock()
    transport.request.side_effect = [
        _instances_response([1, 2], total=5),
        HttpResponse(503, {}, {"message": "unavailable"}),
    ]
    client = MtnCloudClient(
        settings=ClientSettings(token="secret", max_retries=0), transport=transport
    )

    with pytest.raises(ServerError):
        client.instances.list_all(page_size=2)


def test_list_all_rejects_invalid_page_size() -> None:
    client = MtnCloudClient(token="secret", transport=Mock())

    with pytest.raises(ValueError):
        client.instances.list_all(page_size=0)


_NAME_LOOKUP_CASES = [
    ("instances", "instances"),
    ("networks", "networks"),
    ("routers", "networkRouters"),
]


def _named_response(list_key: str, items: list[dict[str, Any]]) -> HttpResponse:
    return HttpResponse(200, {}, {list_key: items})


@pytest.mark.parametrize(("service", "list_key"), _NAME_LOOKUP_CASES)
def test_get_by_name_returns_exact_match(service: str, list_key: str) -> None:
    transport = Mock()
    transport.request.return_value = _named_response(
        list_key, [{"id": 1, "name": "web"}, {"id": 2, "name": "web-2"}]
    )
    client = MtnCloudClient(token="secret", transport=transport)

    result = getattr(client, service).get_by_name("web", zone_id=4, group_id=7)

    assert result.id == 1
    params = transport.request.call_args.kwargs["params"]
    assert params["name"] == "web"
    assert params["zoneId"] == 4
    assert params["siteId"] == 7


@pytest.mark.parametrize(("service", "list_key"), _NAME_LOOKUP_CASES)
def test_get_by_name_raises_lookup_not_found(service: str, list_key: str) -> None:
    transport = Mock()
    transport.request.return_value = _named_response(list_key, [{"id": 2, "name": "web-2"}])
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(LookupNotFoundError, match="'web' was not found"):
        getattr(client, service).get_by_name("web")


@pytest.mark.parametrize(("service", "list_key"), _NAME_LOOKUP_CASES)
def test_get_by_name_rejects_ambiguous_names(service: str, list_key: str) -> None:
    transport = Mock()
    transport.request.return_value = _named_response(
        list_key, [{"id": 5, "name": "web"}, {"id": 3, "name": "web"}]
    )
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(ValueError, match=r"ambiguous: ids \[3, 5\]") as excinfo:
        getattr(client, service).get_by_name("web")

    assert not isinstance(excinfo.value, NotFoundError)
    assert isinstance(excinfo.value, AmbiguousLookupError)


@pytest.mark.parametrize(("service", "list_key"), [("groups", "groups"), ("zones", "zones")])
def test_group_and_zone_ambiguity_lists_ids(service: str, list_key: str) -> None:
    transport = Mock()
    transport.request.return_value = _named_response(
        list_key, [{"id": 7, "name": "prod"}, {"id": 3, "name": "prod"}]
    )
    client = MtnCloudClient(token="secret", transport=transport)

    with pytest.raises(AmbiguousLookupError, match=r"ambiguous: ids \[3, 7\]") as excinfo:
        getattr(client, service).get_by_name("prod")

    assert isinstance(excinfo.value, ValueError)
