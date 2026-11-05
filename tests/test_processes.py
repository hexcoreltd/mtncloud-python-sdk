"""Process discovery and caller-configured polling using synthetic responses."""

from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models import Process, ProcessEvent
from mtn_cloud.modern_exceptions import ForbiddenError, MtnCloudError, NotFoundError
from mtn_cloud.modern_exceptions import TimeoutError as ProcessTimeoutError
from mtn_cloud.transport import HttpResponse


class Clock:
    def __init__(self) -> None:
        self.value = 0.0
        self.delays: list[float] = []

    def __call__(self) -> float:
        return self.value

    def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.value += delay


@pytest.fixture
def transport() -> Mock:
    return Mock()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(transport: Mock, clock: Clock) -> MtnCloudClient:
    return MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
        clock=clock,
        sleeper=clock.sleep,
    )


def response(body: Any, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, body, request_id="req-process")


def detail(status: str | None, **fields: Any) -> HttpResponse:
    return response({"process": {"id": 901, "status": status, **fields}})


def test_process_model_parses_events_metadata_and_provider_status() -> None:
    process = Process.model_validate(
        {
            "id": 901,
            "uniqueId": "process-uuid",
            "processType": {"code": "snapshot"},
            "displayName": "api-01",
            "instanceId": 100,
            "serverId": 7,
            "zoneId": 4,
            "appId": "20",
            "status": "provider-custom",
            "percent": 75.5,
            "statusEta": 20,
            "startDate": "2026-01-01T10:00:00Z",
            "endDate": None,
            "duration": 123,
            "resultType": "unverified-kind",
            "resultId": 81,
            "events": [{"id": 5, "processId": 901, "refType": "instance", "refId": 100}],
        }
    )
    assert process.unique_id == "process-uuid" and process.display_name == "api-01"
    assert process.instance_id == 100 and process.app_id == "20"
    assert process.status == "provider-custom" and process.percent == 75.5
    assert process.start_date is not None and process.end_date is None
    assert process.result_type == "unverified-kind" and process.result_id == 81
    assert isinstance(process.events[0], ProcessEvent) and process.events[0].process_id == 901
    assert Process(id=901).status is None


def test_representations_hide_logs_and_validation_inputs_without_losing_serialization() -> None:
    process = Process.model_validate(
        {
            "id": 901,
            "name": "unit-secret",
            "message": "unit-secret",
            "output": "  unit-secret\n",
            "error": "unit-secret",
            "createdBy": {"username": "unit-secret"},
            "events": [{"id": 5, "output": "unit-secret", "description": "unit-secret"}],
        }
    )
    assert "unit-secret" not in repr(process) + str(process) + repr(process.events[0])
    assert process.model_dump()["output"] == "  unit-secret\n"
    with pytest.raises(ValidationError) as raised:
        Process.model_validate({"id": 901, "events": [{"id": "unit-secret"}]})
    assert "unit-secret" not in str(raised.value)


def test_detail_service_is_lazy_cached_and_checks_requested_instance(
    client: MtnCloudClient, transport: Mock
) -> None:
    assert client._processes is None
    assert client.processes is client.processes
    transport.request.assert_not_called()
    transport.request.return_value = detail("queued", instanceId=100)
    assert client.processes.get(901, instance_id=100).status == "queued"
    assert transport.request.call_args.args == ("GET", "/processes/901")


@pytest.mark.parametrize("instance", [None, 999, True, "100"])
def test_detail_cannot_infer_instance_ownership(
    client: MtnCloudClient, transport: Mock, instance: Any
) -> None:
    transport.request.return_value = detail("complete", instanceId=instance)
    with pytest.raises(MtnCloudError):
        client.processes.get(901, instance_id=100)


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"process": []},
        {"success": False, "process": {"id": 901}},
        {"process": {"id": 902}},
        {"process": {"id": True}},
        {"process": {"id": "901"}},
    ],
)
def test_bad_detail_envelopes_data_and_identity_fail_with_context(
    client: MtnCloudClient, transport: Mock, body: Any
) -> None:
    transport.request.return_value = response(body)
    with pytest.raises(MtnCloudError) as raised:
        client.processes.get(901)
    assert raised.value.method == "GET" and raised.value.path == "/processes/901"


def test_history_translates_only_documented_filters_and_preserves_metadata(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = response(
        {
            "processes": [{"id": 901, "instanceId": 100}],
            "meta": {"offset": 5, "max": 25, "total": 50},
        }
    )
    page = client.processes.list_page(
        instance_id=100, container_id=3, server_id=7, zone_id=4, app_id=20, phrase="snapshot"
    )
    assert (page.offset, page.limit, page.total, page.has_more) == (5, 25, 50, True)
    assert page.items[0].id == 901
    assert transport.request.call_args.kwargs["params"] == {
        "instanceId": 100,
        "containerId": 3,
        "serverId": 7,
        "zoneId": 4,
        "appId": 20,
        "phrase": "snapshot",
    }


def test_list_returns_one_provider_selected_page_without_paging_queries(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = response({"processes": [{"id": 901}], "meta": {"total": 100}})
    assert [item.id for item in client.processes.list()] == [901]
    transport.request.assert_called_once()
    assert transport.request.call_args.kwargs["params"] is None


@pytest.mark.parametrize("filters", [{"limit": 10}, {"offset": 1}, {"group_id": 7}])
def test_unsupported_filters_fail_without_transport(
    client: MtnCloudClient, transport: Mock, filters: dict[str, Any]
) -> None:
    with pytest.raises(TypeError):
        client.processes.list(**filters)
    transport.request.assert_not_called()


@pytest.mark.parametrize("identifier", [True, 0, -1, "100"])
def test_invalid_ids_fail_before_requests(
    client: MtnCloudClient, transport: Mock, identifier: Any
) -> None:
    for operation in (
        lambda: client.processes.get(identifier),
        lambda: client.processes.get(901, instance_id=identifier),
        lambda: client.processes.list(instance_id=identifier),
        lambda: client.processes.wait_for_status(identifier, "complete"),
    ):
        with pytest.raises(ValueError):
            operation()
    transport.request.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"processes": {}},
        {"success": False, "processes": []},
        {"processes": [{"id": "unit-secret"}]},
    ],
)
def test_invalid_history_fails_without_returning_partial_data(
    client: MtnCloudClient, transport: Mock, body: Any
) -> None:
    transport.request.return_value = response(body)
    with pytest.raises(MtnCloudError) as raised:
        client.processes.list()
    assert "unit-secret" not in str(raised.value)


@pytest.mark.parametrize("detail_read", [False, True])
def test_conflicting_event_parent_is_rejected(
    client: MtnCloudClient, transport: Mock, detail_read: bool
) -> None:
    record = {"id": 901, "events": [{"id": 5, "processId": 902}]}
    transport.request.return_value = response(
        {"process": record} if detail_read else {"processes": [record]}
    )
    with pytest.raises(MtnCloudError, match="different parent"):
        if detail_read:
            client.processes.get(901)
        else:
            client.processes.list()


def test_history_rejects_conflicting_instance_but_keeps_missing_references_unknown(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = response({"processes": [{"id": 901}]})
    assert client.processes.list(instance_id=100)[0].instance_id is None
    transport.request.return_value = response({"processes": [{"id": 901, "instanceId": 999}]})
    with pytest.raises(MtnCloudError, match="different instance"):
        client.processes.list(instance_id=100)


def test_polling_uses_explicit_statuses_and_reports_each_observation(
    client: MtnCloudClient, transport: Mock, clock: Clock
) -> None:
    transport.request.side_effect = [
        detail(None, instanceId=100),
        detail("provider-new-state", instanceId=100),
        detail(" COMPLETE ", instanceId=100),
    ]
    seen = []
    result = client.processes.wait_for_status(
        901,
        "Complete",
        instance_id=100,
        failure_statuses={"failed"},
        timeout=20,
        poll_interval=2,
        on_status=lambda process: seen.append(process.status),
    )
    assert result.id == 901 and clock.delays == [2, 2]
    assert seen == [None, "provider-new-state", " COMPLETE "]
    assert all(call.args == ("GET", "/processes/901") for call in transport.request.call_args_list)


def test_there_is_no_implicit_failure_mapping(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = detail("failed", percent=100)
    assert client.processes.wait_for_status(901, "failed").status == "failed"


def test_explicit_failure_avoids_raw_provider_logs(
    client: MtnCloudClient, transport: Mock, clock: Clock
) -> None:
    transport.request.return_value = detail("failed", output="unit-secret", error="unit-secret")
    with pytest.raises(MtnCloudError, match="caller-designated") as raised:
        client.processes.wait_for_status(901, "complete", failure_statuses={"Failed"})
    assert raised.value.response == {"process_id": 901, "last_status": "failed"}
    assert "unit-secret" not in str(raised.value)
    assert clock.delays == []


@pytest.mark.parametrize("status", [None, "running"])
def test_timeout_caps_sleep_and_starts_no_read_at_deadline(
    client: MtnCloudClient, transport: Mock, clock: Clock, status: str | None
) -> None:
    transport.request.return_value = detail(status)
    with pytest.raises(ProcessTimeoutError) as raised:
        client.processes.wait_for_status(901, "complete", timeout=3, poll_interval=2)
    assert raised.value.timeout == 3 and raised.value.path == "/processes/901"
    assert raised.value.response == {"process_id": 901, "last_status": status}
    assert clock.delays == [2, 1] and transport.request.call_count == 2


def test_request_time_can_exceed_polling_budget_without_another_request(
    client: MtnCloudClient, transport: Mock, clock: Clock
) -> None:
    def delayed(*args: Any, **kwargs: Any) -> HttpResponse:
        clock.value = 6
        return detail("running")

    transport.request.side_effect = delayed
    with pytest.raises(ProcessTimeoutError):
        client.processes.wait_for_status(901, "complete", timeout=5)
    transport.request.assert_called_once()
    assert clock.delays == []


@pytest.mark.parametrize(
    "options",
    [
        {"target_status": ""},
        {"target_status": True},
        {"failure_statuses": "failed"},
        {"failure_statuses": None},
        {"failure_statuses": {" "}},
        {"failure_statuses": {"COMPLETE"}},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"timeout": True},
        {"poll_interval": 0},
        {"poll_interval": -1},
        {"poll_interval": float("nan")},
    ],
)
def test_invalid_polling_configuration_fails_before_reads(
    client: MtnCloudClient, transport: Mock, options: dict[str, Any]
) -> None:
    arguments = {"target_status": "complete", **options}
    with pytest.raises(ValueError):
        client.processes.wait_for_status(901, **arguments)
    transport.request.assert_not_called()


@pytest.mark.parametrize("status,error_type", [(403, ForbiddenError), (404, NotFoundError)])
def test_waiter_propagates_read_errors_including_not_found(
    client: MtnCloudClient, transport: Mock, status: int, error_type: type[MtnCloudError]
) -> None:
    transport.request.return_value = response({}, status)
    with pytest.raises(error_type) as raised:
        client.processes.wait_for_status(901, "complete")
    assert raised.value.request_id == "req-process" and raised.value.path == "/processes/901"


def test_callback_failures_propagate_without_repolling(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = detail("running")

    def callback(process: Process) -> None:
        raise RuntimeError("caller callback failed")

    with pytest.raises(RuntimeError, match="caller callback"):
        client.processes.wait_for_status(901, "complete", on_status=callback)
    transport.request.assert_called_once()


def test_callback_cannot_turn_a_running_observation_into_completion(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [detail("running"), detail("complete")]

    def callback(process: Process) -> None:
        process.status = "complete"

    client.processes.wait_for_status(901, "complete", on_status=callback)
    assert transport.request.call_count == 2


def test_integer_sub_id_from_live_contract_is_accepted() -> None:
    # Live MTN contract (2026-11-05): subId is sometimes an integer.
    assert Process.model_validate({"id": 1, "subId": 12}).sub_id == 12
    assert Process.model_validate({"id": 1, "subId": "a-1"}).sub_id == "a-1"
