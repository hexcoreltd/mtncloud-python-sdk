"""Modern image discovery against synthetic, not live-verified, responses."""

from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models import VirtualImage, VirtualImageTag
from mtn_cloud.modern_exceptions import (
    AmbiguousLookupError,
    ForbiddenError,
    LookupNotFoundError,
    MtnCloudError,
    NotFoundError,
    ServerError,
)
from mtn_cloud.services import VirtualImagesService
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
    return HttpResponse(200, {}, {"virtualImages": items, "meta": meta})


def test_image_service_is_lazy_cached_and_client_local(
    client: MtnCloudClient, transport: Mock
) -> None:
    assert client._virtual_images is None
    assert isinstance(client.virtual_images, VirtualImagesService)
    assert client.virtual_images is client.virtual_images
    other = MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="other-unit-test"), transport=Mock()
    )
    assert client.virtual_images is not other.virtual_images
    transport.request.assert_not_called()


def test_list_page_translates_filters_and_metadata(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = page(
        [{"id": 44, "name": "AlmaLinux 10", "imageType": "qcow2"}],
        offset=5,
        max=2,
        total=10,
    )
    result = client.virtual_images.list_page(
        limit=2,
        offset=5,
        name="AlmaLinux 10",
        phrase="Alma",
        image_type="qcow2",
        filter_type="Synced",
    )
    assert isinstance(result.items[0], VirtualImage)
    assert result.items[0].image_type == "qcow2"
    assert (result.offset, result.limit, result.total, result.has_more) == (5, 2, 10, True)
    call = transport.request.call_args
    assert call.args == ("GET", "/virtual-images")
    assert call.kwargs["params"] == {
        "max": 2,
        "offset": 5,
        "name": "AlmaLinux 10",
        "phrase": "Alma",
        "imageType": "qcow2",
        "filterType": "Synced",
    }


def test_default_list_does_not_override_provider_scope(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = page([{"id": 1}])
    assert [image.id for image in client.virtual_images.list()] == [1]
    assert transport.request.call_count == 1
    assert transport.request.call_args.kwargs["params"] == {"offset": 0}


@pytest.mark.parametrize("origin", ["User", "System", "Synced", "All"])
def test_origin_filter_preserves_documented_case(
    client: MtnCloudClient, transport: Mock, origin: Any
) -> None:
    transport.request.return_value = page([])
    client.virtual_images.list(filter_type=origin)
    assert transport.request.call_args.kwargs["params"]["filterType"] == origin


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": True},
        {"limit": 1.5},
        {"offset": -1},
        {"offset": False},
        {"offset": "1"},
        {"filter_type": "public"},
        {"filter_type": "private"},
        {"filter_type": "all"},
    ],
)
def test_invalid_query_is_rejected_before_transport(
    client: MtnCloudClient, transport: Mock, kwargs: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        client.virtual_images.list_page(**kwargs)
    transport.request.assert_not_called()


def test_visibility_is_not_mapped_to_an_origin_filter(
    client: MtnCloudClient, transport: Mock
) -> None:
    with pytest.raises(TypeError):
        client.virtual_images.list(is_public=False)
    transport.request.assert_not_called()


@pytest.mark.parametrize("image_id", [0, -1, True, 1.5, "1"])
def test_get_requires_positive_integer_id(
    client: MtnCloudClient, transport: Mock, image_id: Any
) -> None:
    with pytest.raises(ValueError):
        client.virtual_images.get(image_id)
    transport.request.assert_not_called()


def test_detail_parses_origin_visibility_and_named_tags(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "virtualImage": {
                "id": 44,
                "name": "AlmaLinux 10",
                "imageType": "qcow2",
                "visibility": "private",
                "isPublic": False,
                "systemImage": False,
                "userUploaded": True,
                "userDefined": True,
                "isCloudInit": True,
                "minRam": 1073741824,
                "minDisk": 10737418240,
                "osType": {"name": "AlmaLinux", "code": "almalinux"},
                "tags": [{"name": "environment", "value": "test"}, "legacy-tag"],
                "labels": None,
                "locations": [{"id": 2, "cloud": {"id": 4}, "isPublic": False}],
                "dateCreated": "2026-01-01T10:00:00Z",
                "sshPassword": "must-not-be-retained",
            }
        },
    )
    image = client.virtual_images.get(44)
    assert transport.request.call_args.args == ("GET", "/virtual-images/44")
    assert (image.visibility, image.is_public, image.system_image) == ("private", False, False)
    assert image.user_uploaded and image.user_defined and image.is_cloud_init
    assert (image.os_name, image.os_code) == ("AlmaLinux", "almalinux")
    assert (image.min_ram, image.min_disk) == (1073741824, 10737418240)
    assert image.date_created is not None and image.date_created.year == 2026
    assert image.tags == [VirtualImageTag(name="environment", value="test"), "legacy-tag"]
    assert image.labels == []
    assert image.locations[0]["cloud"] == {"id": 4}
    assert "must-not-be-retained" not in str(image.model_dump())


def test_missing_visibility_and_origin_remain_unknown() -> None:
    image = VirtualImage(id=1, osType=None, minRam=None, minDisk=None)
    assert image.visibility is None and image.is_public is None
    assert image.system_image is None and image.user_uploaded is None
    assert image.os_name is None and image.os_code is None
    assert image.tags == [] and image.locations == []


def test_user_data_is_serializable_but_not_rendered_in_validation_errors() -> None:
    image = VirtualImage(id=1, userData="unit-secret", storageProvider={"key": "unit-secret"})
    assert "unit-secret" not in repr(image) + str(image)
    assert image.model_dump(by_alias=True)["userData"] == "unit-secret"
    assert VirtualImageTag(name="key", value="unit-secret").model_dump()["value"] == "unit-secret"
    with pytest.raises(ValidationError) as raised:
        VirtualImage.model_validate({"id": "unit-secret", "userData": "unit-secret"})
    assert "unit-secret" not in str(raised.value)


def test_name_lookup_traverses_every_page_with_same_filters(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 1, "name": "AlmaLinux 10 old"}], total=2),
        page([{"id": 2, "name": "AlmaLinux 10"}], total=2),
    ]
    image = client.virtual_images.get_by_name("AlmaLinux 10", image_type="qcow2", filter_type="All")
    assert image.id == 2
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {
            "max": 100,
            "offset": offset,
            "name": "AlmaLinux 10",
            "imageType": "qcow2",
            "filterType": "All",
        }
        for offset in (0, 1)
    ]
    assert all(call.args[0] == "GET" for call in transport.request.call_args_list)


def test_name_lookup_reports_missing_and_cross_page_ambiguity(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = page([{"id": 1, "name": "AlmaLinux 10 old"}])
    with pytest.raises(LookupNotFoundError):
        client.virtual_images.get_by_name("AlmaLinux 10")
    transport.request.side_effect = [
        page([{"id": 1, "name": "AlmaLinux 10"}], total=2),
        page([{"id": 2, "name": "AlmaLinux 10"}], total=2),
    ]
    with pytest.raises(AmbiguousLookupError, match=r"ids \[1, 2\]"):
        client.virtual_images.get_by_name("AlmaLinux 10")


def test_name_lookup_does_not_return_match_when_later_page_fails(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 1, "name": "AlmaLinux 10"}], total=2),
        HttpResponse(503, {}, {"message": "busy"}, request_id="req-images"),
    ]
    with pytest.raises(ServerError) as raised:
        client.virtual_images.get_by_name("AlmaLinux 10")
    assert raised.value.request_id == "req-images"


def test_list_all_stops_when_a_provider_ignores_pagination(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = page([{"id": 1}])
    images = client.virtual_images.list_all(page_size=1)
    assert [image.id for image in images] == [1]
    assert transport.request.call_count == 2


def test_overcounted_total_returns_unique_images(client: MtnCloudClient, transport: Mock) -> None:
    # Live MTN contract (2026-11-05): total=2, but offset=1 repeats the only image.
    transport.request.side_effect = [
        page([{"id": 928, "name": "image-a"}], total=2),
        page([{"id": 928, "name": "image-a"}], offset=1, total=2),
    ]
    assert [image.id for image in client.virtual_images.list_all(page_size=1)] == [928]
    assert transport.request.call_count == 2

    transport.request.side_effect = [
        page([{"id": 928, "name": "image-a"}], total=2),
        page([{"id": 928, "name": "image-a"}], offset=1, total=2),
    ]
    assert client.virtual_images.get_by_name("image-a").id == 928


def test_page_size_metadata_is_not_a_collection_total(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        page([{"id": 1}], max=1, size=1),
        page([{"id": 2}], max=1, size=1),
        page([], max=1, size=0),
    ]
    assert [image.id for image in client.virtual_images.list_all()] == [1, 2]
    assert [call.kwargs["params"]["offset"] for call in transport.request.call_args_list] == [
        0,
        1,
        2,
    ]


def test_list_page_without_total_keeps_total_unknown(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = page([{"id": 1}], size=1)
    assert client.virtual_images.list_page().total is None


@pytest.mark.parametrize(
    "body", [None, {}, {"virtualImages": {}}, {"success": False, "virtualImages": []}]
)
def test_invalid_or_rejected_collections_fail(
    client: MtnCloudClient, transport: Mock, body: Any
) -> None:
    transport.request.return_value = HttpResponse(200, {}, body)
    with pytest.raises(MtnCloudError):
        client.virtual_images.list()


@pytest.mark.parametrize(
    "body", [None, {"virtualImage": []}, {"success": False, "virtualImage": {"id": 1}}]
)
def test_invalid_or_rejected_details_fail(
    client: MtnCloudClient, transport: Mock, body: Any
) -> None:
    transport.request.return_value = HttpResponse(200, {}, body)
    with pytest.raises(MtnCloudError):
        client.virtual_images.get(1)


@pytest.mark.parametrize("status,error_type", [(403, ForbiddenError), (404, NotFoundError)])
def test_http_errors_preserve_operation_and_request_id(
    client: MtnCloudClient, transport: Mock, status: int, error_type: type[MtnCloudError]
) -> None:
    transport.request.return_value = HttpResponse(status, {}, {}, request_id="req-images")
    with pytest.raises(error_type) as raised:
        client.virtual_images.get(1)
    assert raised.value.status_code == status
    assert raised.value.request_id == "req-images"
    assert raised.value.path == "/virtual-images/1" and raised.value.method == "GET"
