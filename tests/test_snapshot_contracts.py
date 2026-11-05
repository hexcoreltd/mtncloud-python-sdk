"""Upstream snapshot contract regressions; these responses are synthetic."""

from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models import Snapshot, SnapshotCreate, SnapshotSubmission
from mtn_cloud.modern_exceptions import (
    AmbiguousLookupError,
    ForbiddenError,
    LookupNotFoundError,
    MtnCloudError,
    ServerError,
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
    )


def response(body: Any, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, body, request_id="req-snapshot")


def test_creation_returns_process_ids_from_put_not_a_snapshot(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = response({"success": True, "processIds": [901, 902]})
    submission = client.instances.create_snapshot(
        100, SnapshotCreate(name="pre-upgrade", memory_snapshot=False, for_export=False)
    )
    assert isinstance(submission, SnapshotSubmission)
    assert submission.instance_id == 100 and submission.process_ids == [901, 902]
    assert not hasattr(submission, "id")
    transport.request.assert_called_once()
    call = transport.request.call_args
    assert call.args == ("PUT", "/instances/100/snapshot")
    assert call.kwargs["json"] == {
        "snapshot": {"name": "pre-upgrade", "memorySnapshot": False, "forExport": False}
    }


def test_empty_process_ids_mean_no_tracking_identifiers(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = response({"success": True, "processIds": []})
    assert client.instances.create_snapshot(100, SnapshotCreate(name="manual")).process_ids == []


@pytest.mark.parametrize("process_ids", [None, "901", [True], [0], [-1], ["901"], [1.5]])
def test_invalid_submission_keeps_instance_context_without_provider_inputs(
    client: MtnCloudClient, transport: Mock, process_ids: Any
) -> None:
    transport.request.return_value = response(
        {"success": True, "processIds": process_ids, "password": "unit-secret"}
    )
    with pytest.raises(MtnCloudError, match="Invalid snapshot submission") as raised:
        client.instances.create_snapshot(100, SnapshotCreate(name="manual"))
    assert raised.value.response == {"instance_id": 100}
    assert raised.value.method == "PUT" and raised.value.path == "/instances/100/snapshot"
    assert "unit-secret" not in str(raised.value)


@pytest.mark.parametrize(
    "body", [None, {}, {"success": False}, {"success": "true"}, {"success": 1}]
)
def test_creation_requires_explicit_boolean_acknowledgement(
    client: MtnCloudClient, transport: Mock, body: Any
) -> None:
    transport.request.return_value = response(body)
    with pytest.raises(MtnCloudError, match="did not return success"):
        client.instances.create_snapshot(100, SnapshotCreate(name="manual"))


def test_snapshot_metadata_supports_upstream_and_legacy_shapes() -> None:
    snapshot = Snapshot.model_validate(
        {
            "id": 81,
            "state": "poweredOff",
            "datastore": "primary-store",
            "currentlyActive": True,
            "memorySnapshot": False,
            "forExport": False,
            "forBackup": True,
            "maxStorage": 1024,
            "snapshotCreated": "2026-01-01T10:00:00Z",
            "parentSnapshot": "parent-ref",
            "snapshotFiles": [{"id": 5, "path": "private-path"}],
        }
    )
    assert snapshot.state == "poweredOff" and snapshot.datastore == "primary-store"
    assert snapshot.currently_active is True and snapshot.current is None
    assert snapshot.memory_snapshot is False and snapshot.for_backup is True
    assert snapshot.max_storage == 1024 and snapshot.parent_snapshot == "parent-ref"
    assert snapshot.snapshot_created is not None
    assert "private-path" not in repr(snapshot)
    legacy = Snapshot(id=81, state={"phase": "legacy"}, datastore={"id": 2}, current=True)
    assert legacy.state == {"phase": "legacy"} and legacy.current is True
    assert Snapshot(id=81).currently_active is None


def test_snapshot_models_hide_validation_inputs_and_preserve_explicit_flags() -> None:
    with pytest.raises(ValidationError) as raised:
        Snapshot.model_validate({"id": "invalid-unit-secret"})
    assert "invalid-unit-secret" not in str(raised.value)
    with pytest.raises(ValidationError):
        SnapshotCreate(name="   ")
    request = SnapshotCreate(name="manual", description="unit-secret", forExport=True)
    assert "unit-secret" not in repr(request)
    assert request.to_api_payload() == {
        "snapshot": {"name": "manual", "description": "unit-secret", "forExport": True}
    }


def test_instance_collection_does_not_send_guessed_pagination(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = response({"snapshots": [{"id": 81, "state": "poweredOff"}]})
    assert client.instances.list_snapshots(100)[0].id == 81
    assert transport.request.call_args.args == ("GET", "/instances/100/snapshots")
    assert transport.request.call_args.kwargs["params"] is None


@pytest.mark.parametrize("body", [None, {}, {"snapshots": {}}, {"success": False, "snapshots": []}])
def test_bad_collection_envelopes_fail_with_operation_context(
    client: MtnCloudClient, transport: Mock, body: Any
) -> None:
    transport.request.return_value = response(body)
    with pytest.raises(MtnCloudError) as raised:
        client.instances.list_snapshots(100)
    assert raised.value.path == "/instances/100/snapshots"


@pytest.mark.parametrize("snapshot_id", [None, 0, -1, True, "81"])
def test_bad_collection_ids_are_rejected(
    client: MtnCloudClient, transport: Mock, snapshot_id: Any
) -> None:
    transport.request.return_value = response({"snapshots": [{"id": snapshot_id}]})
    with pytest.raises(MtnCloudError, match="identifier"):
        client.instances.list_snapshots(100)


def test_lookup_requires_unique_id_and_exact_name(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = response({"snapshots": [{"id": 81, "name": "manual-old"}]})
    with pytest.raises(LookupNotFoundError):
        client.instances.get_snapshot_by_name(100, "manual")
    with pytest.raises(LookupNotFoundError):
        client.instances.get_snapshot(100, 82)
    transport.request.return_value = response(
        {"snapshots": [{"id": 81, "name": "manual"}, {"id": 82, "name": "manual"}]}
    )
    with pytest.raises(AmbiguousLookupError):
        client.instances.get_snapshot_by_name(100, "manual")
    assert client.instances.get_snapshot(100, 81).id == 81
    transport.request.return_value = response({"snapshots": [{"id": 81}, {"id": 81}]})
    with pytest.raises(AmbiguousLookupError):
        client.instances.get_snapshot(100, 81)


@pytest.mark.parametrize("method", ["revert_snapshot", "delete_snapshot"])
def test_scoped_mutations_check_membership_and_use_documented_paths(
    client: MtnCloudClient, transport: Mock, method: str
) -> None:
    transport.request.side_effect = [
        response({"snapshots": [{"id": 81}]}),
        response({"success": True}),
    ]
    assert getattr(client.instances, method)(100, 81) is True
    calls = transport.request.call_args_list
    assert calls[0].args == ("GET", "/instances/100/snapshots")
    expected = (
        ("PUT", "/instances/100/revert-snapshot/81")
        if method == "revert_snapshot"
        else ("DELETE", "/snapshots/81")
    )
    assert calls[1].args == expected


@pytest.mark.parametrize("method", ["revert_snapshot", "delete_snapshot"])
@pytest.mark.parametrize("items", [[], [{"id": 81, "instance": {"id": 999}}]])
def test_scoped_mutations_do_not_write_for_missing_or_conflicting_membership(
    client: MtnCloudClient, transport: Mock, method: str, items: list[dict[str, Any]]
) -> None:
    transport.request.return_value = response({"snapshots": items})
    with pytest.raises(MtnCloudError):
        getattr(client.instances, method)(100, 81)
    transport.request.assert_called_once()
    assert transport.request.call_args.args[0] == "GET"


@pytest.mark.parametrize("method", ["revert_snapshot", "delete_snapshot"])
@pytest.mark.parametrize("body", [None, {}, {"success": False}, {"success": "true"}])
def test_scoped_mutations_do_not_report_success_for_unacknowledged_operations(
    client: MtnCloudClient, transport: Mock, method: str, body: Any
) -> None:
    transport.request.side_effect = [response({"snapshots": [{"id": 81}]}), response(body)]
    with pytest.raises(MtnCloudError, match="did not return success"):
        getattr(client.instances, method)(100, 81)


def test_global_snapshot_detail_service_is_cached_and_checks_identity(
    client: MtnCloudClient, transport: Mock
) -> None:
    assert client._snapshots is None
    assert client.snapshots is client.snapshots
    transport.request.return_value = response({"snapshot": {"id": 81, "datastore": "primary"}})
    assert client.snapshots.get(81).datastore == "primary"
    assert transport.request.call_args.args == ("GET", "/snapshots/81")
    transport.request.return_value = response({"snapshot": {"id": 82}})
    with pytest.raises(MtnCloudError, match="different ID"):
        client.snapshots.get(81)


@pytest.mark.parametrize(
    "body", [None, {}, {"snapshot": []}, {"success": False, "snapshot": {"id": 81}}]
)
def test_global_detail_rejects_bad_envelopes(
    client: MtnCloudClient, transport: Mock, body: Any
) -> None:
    transport.request.return_value = response(body)
    with pytest.raises(MtnCloudError):
        client.snapshots.get(81)


@pytest.mark.parametrize("identifier", [0, -1, True, "1"])
def test_invalid_identifiers_fail_before_transport(
    client: MtnCloudClient, transport: Mock, identifier: Any
) -> None:
    operations = [
        lambda: client.instances.list_snapshots(identifier),
        lambda: client.instances.create_snapshot(identifier, SnapshotCreate(name="manual")),
        lambda: client.instances.revert_snapshot(100, identifier),
        lambda: client.instances.delete_snapshot(identifier, 81),
        lambda: client.snapshots.get(identifier),
        lambda: client.snapshots.delete(identifier),
    ]
    for operation in operations:
        with pytest.raises(ValueError):
            operation()
    transport.request.assert_not_called()


@pytest.mark.parametrize("operation", ["create", "revert", "delete"])
def test_mutations_are_never_retried_after_server_errors(transport: Mock, operation: str) -> None:
    client = MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=3),
        transport=transport,
    )
    if operation == "revert":
        transport.request.side_effect = [response({"snapshots": [{"id": 81}]}), response({}, 503)]
    else:
        transport.request.return_value = response({}, 503)
    with pytest.raises(ServerError) as raised:
        if operation == "create":
            client.instances.create_snapshot(100, SnapshotCreate(name="manual"))
        elif operation == "revert":
            client.instances.revert_snapshot(100, 81)
        else:
            client.snapshots.delete(81)
    assert raised.value.request_id == "req-snapshot" and raised.value.attempts == 1
    assert transport.request.call_count == (2 if operation == "revert" else 1)


def test_read_permission_failures_propagate_before_mutation(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.return_value = response({"message": "denied"}, 403)
    with pytest.raises(ForbiddenError) as raised:
        client.instances.delete_snapshot(100, 81)
    assert raised.value.request_id == "req-snapshot"
    assert raised.value.path == "/instances/100/snapshots"
    transport.request.assert_called_once()
