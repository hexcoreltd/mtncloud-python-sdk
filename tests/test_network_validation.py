"""Network create preflight tests; HTTP responses here are synthetic."""

from typing import Any
from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.network import NetworkCreate
from mtn_cloud.modern_exceptions import ForbiddenError, LookupNotFoundError
from mtn_cloud.transport import HttpResponse


def request_model(**changes: Any) -> NetworkCreate:
    values = {
        "name": "private-app",
        "group_id": 1,
        "cloud_id": 2,
        "type_id": 3,
        "resource_pool_id": 4,
        "cidr": "10.20.0.0/24",
        "gateway": "10.20.0.1",
        "dns_primary": "102.88.134.41",
    }
    return NetworkCreate(**{**values, **changes})


def discovery_responses() -> list[HttpResponse]:
    return [
        HttpResponse(200, {}, {"group": {"id": 1, "zones": [{"id": 2}], "active": True}}),
        HttpResponse(200, {}, {"zone": {"id": 2, "enabled": True}}),
        HttpResponse(
            200, {}, {"networkType": {"id": 3, "code": "openstackPrivate", "creatable": True}}
        ),
        HttpResponse(200, {}, {"data": [{"id": 4, "value": "pool-4", "name": "app"}]}),
    ]


@pytest.fixture
def transport() -> Mock:
    return Mock()


@pytest.fixture
def client(transport: Mock) -> MtnCloudClient:
    return MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
    )


def test_validation_uses_scoped_discovery_without_creating_resources(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = discovery_responses()
    assert client.networks.validate_create(request_model()) is None
    assert [call.args[:2] for call in transport.request.call_args_list] == [
        ("GET", "/groups/1"),
        ("GET", "/zones/2"),
        ("GET", "/network-types/3"),
        ("GET", "/options/zonePools"),
    ]
    assert transport.request.call_args.kwargs["params"] == {
        "cloudId": 2,
        "groupId": 1,
        "provisionTypeCode": "openstack",
    }


def test_create_submits_original_payload_only_after_validation(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        *discovery_responses(),
        HttpResponse(201, {}, {"network": {"id": 5, "name": "private-app"}}),
    ]
    request = request_model()
    assert client.networks.create(request, validate=True).id == 5
    assert transport.request.call_args.args == ("POST", "/networks")
    assert transport.request.call_args.kwargs["json"] == request.to_api_payload()


def test_default_create_preserves_existing_single_request_behavior(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = HttpResponse(201, {}, {"network": {"id": 5}})
    assert client.networks.create(request_model()).id == 5
    transport.request.assert_called_once()
    assert transport.request.call_args.args == ("POST", "/networks")


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "  "},
        {"group_id": 0},
        {"cloud_id": -1},
        {"type_id": None},
        {"resource_pool_id": None},
        {"cidr": "not-a-cidr"},
        {"cidr": "10.20.0.1/24"},
        {"gateway": "10.30.0.1"},
        {"gateway": "10.20.0.0"},
        {"gateway": "10.20.0.255"},
        {"gateway": "2001:db8::1"},
        {"gateway": "invalid"},
        {"dns_primary": "resolver.example.test"},
        {"dns_secondary": "999.1.1.1"},
    ],
)
def test_bad_local_inputs_fail_before_discovery_or_creation(
    client: MtnCloudClient, transport: Mock, changes: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        client.networks.create(request_model(**changes), validate=True)
    transport.request.assert_not_called()


@pytest.mark.parametrize(
    ("cidr", "gateway"),
    [("10.20.0.0/31", "10.20.0.0"), ("2001:db8::/64", "2001:db8::1")],
)
def test_address_validation_handles_point_to_point_and_ipv6_networks(
    client: MtnCloudClient, transport: Mock, cidr: str, gateway: str
) -> None:
    transport.request.side_effect = discovery_responses()
    client.networks.validate_create(request_model(cidr=cidr, gateway=gateway))
    assert transport.request.call_count == 4


@pytest.mark.parametrize(
    ("index", "replacement", "message"),
    [
        (0, {"group": {"id": 1, "active": False}}, "inactive"),
        (0, {"group": {"id": 1, "zones": [{"id": 99}]}}, "not associated"),
        (1, {"zone": {"id": 2, "enabled": False}}, "disabled"),
        (1, {"zone": {"id": 2, "status": "disabled"}}, "disabled"),
        (2, {"networkType": {"id": 3, "code": "openstack", "creatable": False}}, "creatable"),
        (2, {"networkType": {"id": 3, "code": "azure", "creatable": True}}, "OpenStack"),
        (3, {"data": [{"id": 99, "value": "pool-99"}]}, "not available"),
    ],
)
def test_incompatible_placement_prevents_submission(
    client: MtnCloudClient,
    transport: Mock,
    index: int,
    replacement: dict[str, Any],
    message: str,
) -> None:
    responses = discovery_responses()
    responses[index] = HttpResponse(200, {}, replacement)
    transport.request.side_effect = responses
    with pytest.raises(ValueError, match=message):
        client.networks.create(request_model(), validate=True)
    assert all(call.args[0] == "GET" for call in transport.request.call_args_list)


@pytest.mark.parametrize("index", [0, 2, 3])
def test_discovery_permission_failures_are_not_bypassed(
    client: MtnCloudClient, transport: Mock, index: int
) -> None:
    responses = discovery_responses()
    responses[index] = HttpResponse(403, {}, {"message": "denied"}, request_id="req-denied")
    transport.request.side_effect = responses
    with pytest.raises(ForbiddenError) as raised:
        client.networks.create(request_model(), validate=True)
    assert raised.value.request_id == "req-denied"
    assert transport.request.call_count == index + 1
    assert all(call.args[0] == "GET" for call in transport.request.call_args_list)


def test_zone_permission_denial_skips_only_the_enabled_check(
    client: MtnCloudClient, transport: Mock
) -> None:
    # Live MTN contract (2026-11-05): tenant credentials get 403 on /zones/{id}.
    responses = discovery_responses()
    responses[1] = HttpResponse(403, {}, {"message": "denied"})
    transport.request.side_effect = responses
    assert client.networks.validate_create(request_model()) is None
    assert [call.args[:2] for call in transport.request.call_args_list] == [
        ("GET", "/groups/1"),
        ("GET", "/zones/2"),
        ("GET", "/network-types/3"),
        ("GET", "/options/zonePools"),
    ]
    assert transport.request.call_args.kwargs["params"]["cloudId"] == 2


def test_zone_outside_the_group_fails_before_the_zone_lookup(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = discovery_responses()
    with pytest.raises(ValueError, match="not associated with group"):
        client.networks.validate_create(request_model(cloud_id=9))
    assert transport.request.call_count == 1


def subnet_page(*subnets: tuple[int, int | None]) -> HttpResponse:
    return HttpResponse(
        200,
        {},
        {
            "subnets": [
                {"id": sid, **({"network": {"id": parent}} if parent is not None else {})}
                for sid, parent in subnets
            ]
        },
    )


def test_subnets_of_another_network_are_never_returned(
    client: MtnCloudClient, transport: Mock
) -> None:
    # Live MTN contract (2026-11-05): just after creating network 720, its
    # subnet listing returned subnet 4442 of network 660 for about 10 seconds.
    transport.request.return_value = subnet_page((4442, 660))
    assert client.networks.list_subnets(720) == []

    transport.request.return_value = subnet_page((4442, 660), (4501, 720), (77, None))
    assert [subnet.id for subnet in client.networks.list_subnets(720)] == [4501, 77]


def test_subnet_lookup_cannot_select_another_networks_subnet(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = subnet_page((4442, 660))
    with pytest.raises(LookupNotFoundError):
        client.networks.get_subnet(720, 4442)
