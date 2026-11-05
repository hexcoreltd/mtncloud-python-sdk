"""Router lifecycle regressions using synthetic HTTP responses, not live fixtures."""

from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.router import RouterCreate
from mtn_cloud.modern_exceptions import (
    ForbiddenError,
    MtnCloudError,
    NotFoundError,
    ServerError,
    TimeoutError,
)
from mtn_cloud.transport import HttpResponse


@pytest.fixture
def transport() -> Mock:
    return Mock()


@pytest.fixture
def client(transport: Mock) -> MtnCloudClient:
    return MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
        sleeper=Mock(),
    )


@pytest.fixture
def request_model() -> RouterCreate:
    return RouterCreate(
        name="test-router",
        group_id=1,
        cloud_id=2,
        resource_pool_id=3,
        internal_subnet_ids=[4],
    )


def router_response(status: str = "ok", code: str = "neutronRouter") -> HttpResponse:
    return HttpResponse(
        200,
        {},
        {"networkRouter": {"id": 42, "status": status, "type": {"id": 5, "code": code}}},
    )


@pytest.mark.parametrize(
    ("status", "error_type"), [(403, ForbiddenError), (404, NotFoundError), (503, ServerError)]
)
def test_create_retains_submitted_id_and_http_error_metadata(
    client: MtnCloudClient,
    transport: Mock,
    request_model: RouterCreate,
    status: int,
    error_type: type[MtnCloudError],
) -> None:
    transport.request.side_effect = [
        HttpResponse(200, {}, {"success": True, "id": 42}),
        HttpResponse(status, {}, {"message": "read failed"}, request_id="req-1"),
    ]
    with pytest.raises(error_type) as raised:
        client.routers.create(request_model, router_type_id=5)
    error = raised.value
    assert error.response == {"message": "read failed", "router_id": 42}
    assert (error.status_code, error.method, error.path, error.request_id, error.attempts) == (
        status,
        "GET",
        "/networks/routers/42",
        "req-1",
        1,
    )
    assert [call.args[0] for call in transport.request.call_args_list] == ["POST", "GET"]


def test_create_retains_cleanup_id_when_detail_model_is_invalid(
    client: MtnCloudClient, transport: Mock, request_model: RouterCreate
) -> None:
    transport.request.side_effect = [
        HttpResponse(200, {}, {"success": True, "id": 42}),
        HttpResponse(200, {}, {"networkRouter": {"id": "bad-id"}}),
    ]
    with pytest.raises(MtnCloudError, match="invalid detail response") as raised:
        client.routers.create(request_model, router_type_id=5)
    assert raised.value.response == {"router_id": 42}
    assert raised.value.__cause__ is not None


def test_failed_post_has_no_assumed_cleanup_id(
    client: MtnCloudClient, transport: Mock, request_model: RouterCreate
) -> None:
    transport.request.return_value = HttpResponse(503, {}, {"message": "busy"})
    with pytest.raises(ServerError) as raised:
        client.routers.create(request_model, router_type_id=5)
    assert raised.value.response == {"message": "busy"}
    transport.request.assert_called_once()


@pytest.mark.parametrize("option", ["timeout", "poll_interval"])
@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_create_validates_wait_options_before_any_http_request(
    client: MtnCloudClient,
    transport: Mock,
    request_model: RouterCreate,
    option: str,
    value: float,
) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        client.routers.create(request_model, wait=True, **{option: value})
    transport.request.assert_not_called()


def test_create_wait_failure_retains_cleanup_id(
    client: MtnCloudClient, transport: Mock, request_model: RouterCreate
) -> None:
    transport.request.side_effect = [
        HttpResponse(200, {}, {"success": True, "id": 42}),
        router_response("provisioning"),
        router_response("failed"),
    ]
    with pytest.raises(MtnCloudError, match="provisioning failed") as raised:
        client.routers.create(request_model, router_type_id=5, wait=True)
    assert raised.value.response == {"router_id": 42, "status": "failed"}


@pytest.mark.parametrize("delete_race", [False, True])
def test_delete_is_idempotent_when_resource_disappears(
    client: MtnCloudClient, transport: Mock, delete_race: bool
) -> None:
    missing = HttpResponse(404, {}, {"message": "missing"})
    transport.request.side_effect = [router_response(), missing] if delete_race else [missing]
    assert client.routers.delete(42) is True
    assert transport.request.call_count == (2 if delete_race else 1)


@pytest.mark.parametrize("status", [403, 409, 500])
@pytest.mark.parametrize("during_delete", [False, True])
def test_delete_propagates_other_http_errors(
    client: MtnCloudClient, transport: Mock, status: int, during_delete: bool
) -> None:
    failure = HttpResponse(status, {}, {"message": "rejected"}, request_id="req-delete")
    transport.request.side_effect = [router_response(), failure] if during_delete else [failure]
    with pytest.raises(MtnCloudError) as raised:
        client.routers.delete(42)
    assert raised.value.status_code == status
    assert raised.value.request_id == "req-delete"
    assert raised.value.response == {"message": "rejected", "router_id": 42}


def test_delete_does_not_accept_success_false(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.side_effect = [router_response(), HttpResponse(200, {}, {"success": False})]
    with pytest.raises(MtnCloudError, match="deletion was rejected") as raised:
        client.routers.delete(42)
    assert raised.value.response == {"success": False, "router_id": 42}


def test_delete_refuses_other_provider_types(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = router_response(code="other")
    with pytest.raises(ValueError, match="not an MTN neutronRouter"):
        client.routers.delete(42)
    transport.request.assert_called_once()


@pytest.mark.parametrize("method", ["wait_until_ready", "wait_until_deleted"])
def test_waiter_timeout_preserves_cleanup_id(transport: Mock, method: str) -> None:
    client = MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
        sleeper=Mock(),
        clock=Mock(side_effect=[0, 5]),
    )
    transport.request.return_value = router_response("provisioning")
    with pytest.raises(TimeoutError) as raised:
        getattr(client.routers, method)(42, timeout=5, poll_interval=1)
    assert raised.value.timeout == 5
    assert raised.value.response["router_id"] == 42


def test_readiness_waiter_observes_transition_and_limits_sleep(transport: Mock) -> None:
    sleeper = Mock()
    client = MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
        sleeper=sleeper,
        clock=Mock(side_effect=[0, 4]),
    )
    transport.request.side_effect = [router_response("provisioning"), router_response("active")]
    assert client.routers.wait_until_ready(42, timeout=5, poll_interval=10).status == "active"
    sleeper.assert_called_once_with(1)


def test_deletion_waiter_confirms_absence(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = HttpResponse(404, {}, {"message": "gone"})
    assert client.routers.wait_until_deleted(42) is True
