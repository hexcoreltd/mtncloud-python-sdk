"""Backup pagination and submission regressions with synthetic responses."""

from typing import Any
from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.modern_exceptions import ForbiddenError, MtnCloudError, ServerError
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


def run_operation(client: MtnCloudClient, operation: str) -> Any:
    if operation == "execute":
        return client.backups.execute(7)
    if operation == "execute_job":
        return client.backups.execute_job(9)
    if operation == "delete":
        return client.backups.delete(7)
    if operation == "get_job":
        return client.backups.get_job(9)
    if operation == "get":
        return client.backups.get(7)
    if operation == "list":
        return client.backups.list()
    if operation == "results":
        return client.backups.list_results(7)
    return client.backups.list_jobs()


@pytest.mark.parametrize("kind", ["results", "jobs"])
def test_typed_pages_preserve_metadata(client: MtnCloudClient, transport: Mock, kind: str) -> None:
    transport.request.return_value = HttpResponse(
        200, {}, {kind: [{"id": 1}], "meta": {"max": 2, "offset": 5, "total": 10}}
    )
    page = (
        client.backups.list_results_page(7, limit=2, offset=5)
        if kind == "results"
        else client.backups.list_jobs_page(limit=2, offset=5)
    )
    assert (page.offset, page.limit, page.total) == (5, 2, 10)
    assert page.items[0].id == 1
    assert page.has_more
    assert transport.request.call_args.kwargs["params"] == {"max": 2, "offset": 5}


def test_missing_metadata_falls_back_to_requested_offset_and_limit(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = HttpResponse(200, {}, {"results": [{"id": 1}]})
    page = client.backups.list_results_page(7, limit=3, offset=6)
    assert (page.offset, page.limit, page.total) == (6, 3, None)


def test_zero_total_is_not_replaced_by_size_alias(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = HttpResponse(
        200, {}, {"jobs": [], "meta": {"total": 0, "size": 99}}
    )
    assert client.backups.list_jobs_page().total == 0


@pytest.mark.parametrize("kind", ["results", "jobs"])
def test_all_page_helpers_traverse_collections(
    client: MtnCloudClient, transport: Mock, kind: str
) -> None:
    transport.request.side_effect = [
        HttpResponse(200, {}, {kind: [{"id": 1}, {"id": 2}], "meta": {"total": 3}}),
        HttpResponse(200, {}, {kind: [{"id": 3}], "meta": {"total": 3}}),
    ]
    items = (
        client.backups.list_all_results(7, page_size=2)
        if kind == "results"
        else client.backups.list_all_jobs(page_size=2)
    )
    assert [item.id for item in items] == [1, 2, 3]
    calls = transport.request.call_args_list
    assert calls[1].kwargs["params"] == {"max": 2, "offset": 2}
    expected_path = "/backups/7/results" if kind == "results" else "/backups/jobs"
    assert all(call.args == ("GET", expected_path) for call in calls)


@pytest.mark.parametrize("kind", ["results", "jobs"])
def test_all_page_helpers_propagate_later_failures_without_partial_history(
    client: MtnCloudClient, transport: Mock, kind: str
) -> None:
    transport.request.side_effect = [
        HttpResponse(200, {}, {kind: [{"id": 1}], "meta": {"total": 2}}),
        HttpResponse(403, {}, {"message": "denied"}, request_id="req-backup"),
    ]
    with pytest.raises(ForbiddenError) as raised:
        if kind == "results":
            client.backups.list_all_results(7, page_size=1)
        else:
            client.backups.list_all_jobs(page_size=1)
    assert raised.value.request_id == "req-backup"


def test_single_result_list_preserves_existing_default_request(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = HttpResponse(
        200, {}, {"results": [{"id": 1}], "meta": {"total": 2}}
    )
    assert len(client.backups.list_results(7)) == 1
    transport.request.assert_called_once()
    assert transport.request.call_args.kwargs["params"] is None


def test_result_parent_mismatch_is_rejected(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = HttpResponse(200, {}, {"results": [{"id": 1, "backupId": 99}]})
    with pytest.raises(MtnCloudError, match="different parent"):
        client.backups.list_results(7)


@pytest.mark.parametrize(
    "operation", ["execute", "execute_job", "delete", "get", "get_job", "list", "results", "jobs"]
)
def test_explicit_rejected_envelopes_are_never_accepted(
    client: MtnCloudClient, transport: Mock, operation: str
) -> None:
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "success": False,
            "message": "unit-secret",
            "backup": {"id": 7},
            "job": {"id": 9},
            "backups": [],
            "results": [],
            "jobs": [],
        },
    )
    with pytest.raises(MtnCloudError, match="rejected") as raised:
        run_operation(client, operation)
    assert "unit-secret" not in str(raised.value)
    assert raised.value.method in {"GET", "POST", "DELETE"}
    assert raised.value.path.startswith("/backups")


@pytest.mark.parametrize("operation", ["execute", "execute_job"])
@pytest.mark.parametrize("body", [None, "invalid", []])
def test_non_object_execution_response_is_invalid(
    client: MtnCloudClient, transport: Mock, operation: str, body: Any
) -> None:
    transport.request.return_value = HttpResponse(202, {}, body)
    with pytest.raises(MtnCloudError, match="Invalid"):
        run_operation(client, operation)


@pytest.mark.parametrize("operation", ["execute", "execute_job"])
def test_submission_response_is_returned_without_inventing_completion(
    client: MtnCloudClient, transport: Mock, operation: str
) -> None:
    body = {"success": True, "status": "queued", "id": 19}
    transport.request.return_value = HttpResponse(202, {}, body)
    assert run_operation(client, operation) == body
    transport.request.assert_called_once()


@pytest.mark.parametrize("operation", ["execute", "execute_job", "delete"])
def test_mutations_are_not_retried(transport: Mock, operation: str) -> None:
    client = MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=3),
        transport=transport,
        sleeper=Mock(),
    )
    transport.request.return_value = HttpResponse(503, {}, {"message": "busy"})
    with pytest.raises(ServerError):
        run_operation(client, operation)
    transport.request.assert_called_once()


@pytest.mark.parametrize("kind", ["backup", "results", "jobs"])
@pytest.mark.parametrize("options", [{"limit": 0}, {"offset": -1}, {"limit": True}])
def test_bad_pagination_fails_before_request(
    client: MtnCloudClient, transport: Mock, kind: str, options: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        if kind == "backup":
            client.backups.list_page(**options)
        elif kind == "results":
            client.backups.list_results_page(7, **options)
        else:
            client.backups.list_jobs_page(**options)
    transport.request.assert_not_called()


@pytest.mark.parametrize("kind", ["results", "jobs"])
def test_bad_page_size_fails_before_request(
    client: MtnCloudClient, transport: Mock, kind: str
) -> None:
    with pytest.raises(ValueError):
        if kind == "results":
            client.backups.list_all_results(7, page_size=0)
        else:
            client.backups.list_all_jobs(page_size=0)
    transport.request.assert_not_called()


@pytest.mark.parametrize("service,key", [("networks", "networks"), ("volumes", "storageVolumes")])
def test_common_collection_adapter_rejects_failed_envelopes(
    client: MtnCloudClient, transport: Mock, service: str, key: str
) -> None:
    transport.request.return_value = HttpResponse(200, {}, {"success": False, key: []})
    with pytest.raises(MtnCloudError, match="rejected"):
        getattr(client, service).list()


def test_backup_name_lookup_checks_later_pages(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.side_effect = [
        HttpResponse(
            200, {}, {"backups": [{"id": 1, "name": "nightly-old"}], "meta": {"total": 2}}
        ),
        HttpResponse(200, {}, {"backups": [{"id": 2, "name": "nightly"}], "meta": {"total": 2}}),
    ]
    assert client.backups.get_by_name("nightly").id == 2
    assert transport.request.call_args.kwargs["params"] == {
        "max": 100,
        "offset": 1,
        "phrase": "nightly",
    }
