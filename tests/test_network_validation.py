"""Network create preflight tests; HTTP responses here are synthetic."""

from typing import Any
from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.network import NetworkCreate
from mtn_cloud.modern_exceptions import ForbiddenError
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


@pytest.mark.parametrize("index", range(4))
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
