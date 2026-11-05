"""Block-storage selection regressions with synthetic transport responses."""

from typing import Any
from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.volume import StorageVolume, Volume
from mtn_cloud.modern_exceptions import AmbiguousLookupError, ForbiddenError, LookupNotFoundError
from mtn_cloud.transport import HttpResponse


@pytest.mark.parametrize(
    ("fields", "state", "available"),
    [
        ({}, "unknown", False),
        ({"status": "available"}, "unknown", False),
        ({"instanceId": None}, "unattached", False),
        ({"instanceId": None, "status": ""}, "unattached", False),
        ({"instanceId": None, "status": "available"}, "unattached", True),
        ({"instanceId": None, "status": "PROVISIONED"}, "unattached", True),
        ({"instanceId": None, "status": "ready"}, "unattached", True),
        ({"instanceId": None, "status": "failed"}, "unattached", False),
        ({"instanceId": None, "status": "deleting"}, "unattached", False),
        ({"instanceId": None, "status": "attached"}, "unattached", False),
        ({"instanceId": 10, "status": "available"}, "attached", False),
        ({"instance_id": None, "status": "ready"}, "unattached", True),
        ({"instance_id": 10}, "attached", False),
    ],
)
def test_attachment_evidence_and_availability_hint(
    fields: dict[str, Any], state: str, available: bool
) -> None:
    volume = StorageVolume.model_validate({"id": 1, **fields})
    assert volume.attachment_state == state
    assert volume.is_attached is (state == "attached")
    assert volume.is_unattached is (state == "unattached")
    assert volume.is_available is available


def test_legacy_alias_and_serialization_preserving_unset_fields() -> None:
    assert Volume is StorageVolume
    unknown = Volume(id=1)
    unattached = Volume(id=2, instance_id=None)
    assert (
        StorageVolume.model_validate(unknown.model_dump(exclude_unset=True)).attachment_state
        == "unknown"
    )
    assert StorageVolume.model_validate(unattached.model_dump(exclude_unset=True)).is_unattached


@pytest.fixture
def transport() -> Mock:
    return Mock()


@pytest.fixture
def client(transport: Mock) -> MtnCloudClient:
    return MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
    )


def page(items: list[dict[str, Any]], offset: int, total: int) -> HttpResponse:
    return HttpResponse(
        200, {}, {"storageVolumes": items, "meta": {"offset": offset, "total": total}}
    )


def test_name_lookup_searches_later_pages_and_preserves_zone_scope(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 1, "name": "data-old"}], 0, 2),
        page([{"id": 2, "name": "data"}], 1, 2),
    ]
    assert client.volumes.get_by_name("data", zone_id=4).id == 2
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": 0, "phrase": "data", "zoneId": 4},
        {"max": 100, "offset": 1, "phrase": "data", "zoneId": 4},
    ]


def test_duplicate_names_on_different_pages_are_ambiguous(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 2, "name": "data"}], 0, 2),
        page([{"id": 1, "name": "data"}], 1, 2),
    ]
    with pytest.raises(AmbiguousLookupError, match=r"ids \[1, 2\]") as raised:
        client.volumes.get_by_name("data")
    assert isinstance(raised.value, ValueError)


def test_name_lookup_requires_exact_match(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = page([{"id": 1, "name": "data-old"}], 0, 1)
    with pytest.raises(LookupNotFoundError):
        client.volumes.get_by_name("data")


def test_unattached_selection_uses_all_pages_and_excludes_unknowns(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page(
            [
                {"id": 1, "status": "available"},
                {"id": 2, "instanceId": 10, "status": "available"},
            ],
            0,
            4,
        ),
        page(
            [
                {"id": 3, "instanceId": None, "status": "ready"},
                {"id": 4, "instanceId": None, "status": "failed"},
            ],
            2,
            4,
        ),
    ]
    volumes = client.volumes.list_unattached(zone_id=4)
    assert [volume.id for volume in volumes] == [3, 4]
    assert [volume.is_available for volume in volumes] == [True, False]
    assert [call.kwargs["params"]["zoneId"] for call in transport.request.call_args_list] == [4, 4]


def test_attached_listing_preserves_filter_across_pages(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 1, "instanceId": 10}], 0, 2),
        page([{"id": 2, "instanceId": 10}], 1, 2),
    ]
    assert [volume.id for volume in client.volumes.list_attached(10)] == [1, 2]
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": 0, "instanceId": 10},
        {"max": 100, "offset": 1, "instanceId": 10},
    ]


@pytest.mark.parametrize("operation", ["get_by_name", "list_unattached", "list_attached"])
def test_later_page_errors_propagate_instead_of_returning_partial_selections(
    client: MtnCloudClient, transport: Mock, operation: str
) -> None:
    transport.request.side_effect = [
        page([{"id": 1, "name": "data", "instanceId": None}], 0, 2),
        HttpResponse(403, {}, {"message": "denied"}, request_id="req-2"),
    ]
    with pytest.raises(ForbiddenError) as raised:
        if operation == "get_by_name":
            client.volumes.get_by_name("data")
        elif operation == "list_attached":
            client.volumes.list_attached(10)
        else:
            client.volumes.list_unattached()
    assert raised.value.request_id == "req-2"


def test_list_still_returns_a_single_page(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = page([{"id": 1}], 0, 2)
    assert len(client.volumes.list(limit=1)) == 1
    transport.request.assert_called_once()
