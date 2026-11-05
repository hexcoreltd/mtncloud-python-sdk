"""Dependency lookups must traverse collections before selecting a placement."""

from typing import Any
from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.modern_exceptions import AmbiguousLookupError, NotFoundError, ServerError
from mtn_cloud.transport import HttpResponse

CASES = [
    ("groups", "groups", "name", "get_by_name"),
    ("zones", "zones", "name", "get_by_name"),
    ("instance_types", "instanceTypes", "name", "get_by_name"),
    ("instance_types", "instanceTypes", "code", "get_by_code"),
]


def item(resource_id: int, field: str, value: str) -> dict[str, Any]:
    return {"id": resource_id, "code": "alma", field: value}


def make_client(transport: Mock) -> MtnCloudClient:
    return MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
    )


@pytest.mark.parametrize("service,key,field,method", CASES)
@pytest.mark.parametrize("ambiguous", [False, True])
def test_dependency_lookup_checks_later_pages_and_retains_filter(
    service: str, key: str, field: str, method: str, ambiguous: bool
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(
            200, {}, {key: [item(1, field, "alma" if ambiguous else "other")], "meta": {"total": 2}}
        ),
        HttpResponse(200, {}, {key: [item(2, field, "alma")], "meta": {"total": 2}}),
    ]
    lookup = getattr(getattr(make_client(transport), service), method)
    if ambiguous:
        with pytest.raises(AmbiguousLookupError):
            lookup("alma")
    else:
        assert lookup("alma").id == 2
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": offset, field: "alma"} for offset in (0, 1)
    ]


@pytest.mark.parametrize("service,key,field,method", CASES)
def test_dependency_lookup_does_not_return_a_match_after_later_page_failure(
    service: str, key: str, field: str, method: str
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {key: [item(1, field, "alma")], "meta": {"total": 2}}),
        HttpResponse(503, {}, {}, request_id="req-later-page"),
    ]
    lookup = getattr(getattr(make_client(transport), service), method)
    with pytest.raises(ServerError) as raised:
        lookup("alma")
    assert raised.value.request_id == "req-later-page"


@pytest.mark.parametrize("service,key,field,method", CASES)
def test_dependency_lookup_requires_exact_match(
    service: str, key: str, field: str, method: str
) -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(200, {}, {key: [item(1, field, "alma-old")]})
    lookup = getattr(getattr(make_client(transport), service), method)
    with pytest.raises(NotFoundError):
        lookup("alma")
