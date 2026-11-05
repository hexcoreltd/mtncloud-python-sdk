"""Application discovery and pagination regressions using synthetic responses."""

from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.app import Application
from mtn_cloud.modern_exceptions import AmbiguousLookupError, LookupNotFoundError, MtnCloudError
from mtn_cloud.transport import HttpResponse


@pytest.fixture
def transport() -> Mock:
    return Mock()


@pytest.fixture
def client(transport: Mock) -> MtnCloudClient:
    return MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
    )


def page(items: list[dict[str, Any]], **meta: Any) -> HttpResponse:
    return HttpResponse(200, {}, {"apps": items, "meta": meta})


def test_application_name_lookup_follows_pages_and_preserves_group(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 1, "name": "ledger-old"}], total=2),
        page([{"id": 2, "name": "ledger"}], total=2),
    ]
    assert client.apps.get_by_name("ledger", group_id=7).id == 2
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": 0, "name": "ledger", "siteId": 7},
        {"max": 100, "offset": 1, "name": "ledger", "siteId": 7},
    ]


def test_application_name_requires_exact_unique_match(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = page([{"id": 1, "name": "ledger-old"}])
    with pytest.raises(LookupNotFoundError):
        client.apps.get_by_name("ledger")
    transport.request.side_effect = [
        page([{"id": 1, "name": "ledger"}], total=2),
        page([{"id": 2, "name": "ledger"}], total=2),
    ]
    with pytest.raises(AmbiguousLookupError):
        client.apps.get_by_name("ledger")


def test_a_page_with_no_new_ids_ends_pagination_before_a_third_request(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 1}]),
        page([{"id": 1}]),
        AssertionError("pagination must stop"),
    ]
    apps = client.apps.list_all(page_size=1)
    assert [app.id for app in apps] == [1]
    assert transport.request.call_count == 2


def test_partially_overlapping_pages_are_deduplicated(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 1}, {"id": 2}], total=4),
        page([{"id": 2}, {"id": 3}], total=4),
        AssertionError("offset reached the reported total"),
    ]
    apps = client.apps.list_all(page_size=2)
    assert [app.id for app in apps] == [1, 2, 3]
    assert transport.request.call_count == 2


def test_reported_offset_mismatch_is_rejected(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = page([{"id": 1}], offset=9)
    with pytest.raises(MtnCloudError, match="unexpected offset"):
        client.apps.list_all()


def test_reported_page_cap_is_used_without_a_total(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.side_effect = [
        page([{"id": 1}], max=1),
        page([{"id": 2}], max=1),
        page([], max=1),
    ]
    assert [item.id for item in client.apps.list_all(page_size=100)] == [1, 2]
    assert [call.kwargs["params"]["offset"] for call in transport.request.call_args_list] == [
        0,
        1,
        2,
    ]


@pytest.mark.parametrize("size", [0, -1, True, 1.5])
def test_invalid_page_size_rejected_before_requests(
    client: MtnCloudClient, transport: Mock, size: Any
) -> None:
    with pytest.raises(ValueError):
        client.apps.list_all(page_size=size)
    transport.request.assert_not_called()


def test_progress_guard_is_local_to_each_operation(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = page([{"id": 1}])
    assert len(client.apps.list_all()) == 1
    assert len(client.apps.list_all()) == 1


def test_application_config_stays_serializable_without_rendering_validation_inputs() -> None:
    application = Application(id=1, config={"secret": "unit-secret"})
    assert "unit-secret" not in repr(application) + str(application)
    assert application.model_dump()["config"] == {"secret": "unit-secret"}
    with pytest.raises(ValidationError) as raised:
        Application.model_validate({"config": {"secret": "unit-secret"}})
    assert "unit-secret" not in str(raised.value)
