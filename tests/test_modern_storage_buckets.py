"""Storage configuration regressions using synthetic HTTP responses."""

from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError as ModelValidationError

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.storage_bucket import StorageBucket, StorageBucketCreate, StorageBucketUpdate
from mtn_cloud.modern_exceptions import (
    AmbiguousLookupError,
    ForbiddenError,
    LookupNotFoundError,
    MtnCloudError,
    ServerError,
)
from mtn_cloud.transport import HttpResponse

CONFIG = {
    "accessKey": "unit-access",
    "secretKey": "unit-secret",
    "endpoint": "https://s3.example.test",
}


@pytest.fixture
def transport() -> Mock:
    return Mock()


@pytest.fixture
def client(transport: Mock) -> MtnCloudClient:
    return MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=0),
        transport=transport,
    )


def invoke(client: MtnCloudClient, operation: str) -> Any:
    if operation == "create":
        return client.storage_buckets.create(
            StorageBucketCreate(name="backup", bucket_name="backup", config=CONFIG)
        )
    if operation == "update":
        return client.storage_buckets.update(7, StorageBucketUpdate(copy_to_store=False))
    if operation == "get":
        return client.storage_buckets.get(7)
    return client.storage_buckets.delete(7)


def test_name_lookup_follows_pages(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.side_effect = [
        HttpResponse(
            200, {}, {"storageBuckets": [{"id": 1, "name": "backup-old"}], "meta": {"total": 2}}
        ),
        HttpResponse(
            200, {}, {"storageBuckets": [{"id": 7, "name": "backup"}], "meta": {"total": 2}}
        ),
    ]
    assert client.storage_buckets.get_by_name("backup").id == 7
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": 0, "name": "backup"},
        {"max": 100, "offset": 1, "name": "backup"},
    ]


def test_duplicate_names_across_pages_are_ambiguous(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        HttpResponse(
            200, {}, {"storageBuckets": [{"id": 1, "name": "backup"}], "meta": {"total": 2}}
        ),
        HttpResponse(
            200, {}, {"storageBuckets": [{"id": 7, "name": "backup"}], "meta": {"total": 2}}
        ),
    ]
    with pytest.raises(AmbiguousLookupError, match=r"ids \[1, 7\]"):
        client.storage_buckets.get_by_name("backup")


def test_name_lookup_rejects_partial_match(client: MtnCloudClient, transport: Mock) -> None:
    transport.request.return_value = HttpResponse(
        200, {}, {"storageBuckets": [{"id": 1, "name": "backup-old"}]}
    )
    with pytest.raises(LookupNotFoundError):
        client.storage_buckets.get_by_name("backup")


def test_later_page_failure_does_not_return_a_false_unique_match(
    client: MtnCloudClient, transport: Mock
) -> None:
    transport.request.side_effect = [
        HttpResponse(
            200, {}, {"storageBuckets": [{"id": 7, "name": "backup"}], "meta": {"total": 2}}
        ),
        HttpResponse(403, {}, {"message": "denied"}, request_id="req-2"),
    ]
    with pytest.raises(ForbiddenError) as raised:
        client.storage_buckets.get_by_name("backup")
    assert raised.value.request_id == "req-2"


@pytest.mark.parametrize("operation", ["create", "update", "get", "delete"])
def test_explicit_rejection_is_not_treated_as_success(
    client: MtnCloudClient, transport: Mock, operation: str
) -> None:
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "success": False,
            "message": "unit-secret",
            "config": CONFIG,
            "storageBucket": {"id": 7, "name": "backup"},
        },
    )
    with pytest.raises(MtnCloudError, match="operation was rejected") as raised:
        invoke(client, operation)
    error = raised.value
    assert "unit-secret" not in str(error)
    assert "unit-access" not in str(error.response)
    assert error.response == (None if operation == "create" else {"bucket_id": 7})
    assert error.path == ("/storage-buckets" if operation == "create" else "/storage-buckets/7")


@pytest.mark.parametrize("operation", ["create", "update", "get"])
@pytest.mark.parametrize(
    "body", [None, "unit-secret", {"storageBucket": None}, {"storageBucket": {"config": CONFIG}}]
)
def test_malformed_detail_responses_raise_sdk_errors_without_payload_in_message(
    client: MtnCloudClient, transport: Mock, operation: str, body: Any
) -> None:
    transport.request.return_value = HttpResponse(200, {}, body)
    with pytest.raises(MtnCloudError, match="Invalid storage-bucket response") as raised:
        invoke(client, operation)
    assert "unit-secret" not in str(raised.value)
    assert "unit-access" not in str(raised.value.response)


@pytest.mark.parametrize("remove_resources", [False, True])
@pytest.mark.parametrize(
    ("status", "body"), [(204, None), (200, {"success": True}), (404, {"message": "gone"})]
)
def test_delete_preserves_explicit_resource_removal_intent(
    client: MtnCloudClient, transport: Mock, remove_resources: bool, status: int, body: Any
) -> None:
    transport.request.return_value = HttpResponse(status, {}, body)
    assert client.storage_buckets.delete(7, remove_resources=remove_resources) is True
    transport.request.assert_called_once()
    assert transport.request.call_args.args == ("DELETE", "/storage-buckets/7")
    assert transport.request.call_args.kwargs["params"] == (
        {"removeResources": True} if remove_resources else None
    )


@pytest.mark.parametrize("operation", ["create", "update", "get", "delete"])
def test_http_errors_keep_their_class_and_metadata(
    client: MtnCloudClient, transport: Mock, operation: str
) -> None:
    transport.request.return_value = HttpResponse(
        403, {}, {"message": "denied"}, request_id="req-1"
    )
    with pytest.raises(ForbiddenError) as raised:
        invoke(client, operation)
    assert raised.value.status_code == 403
    assert raised.value.request_id == "req-1"


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_mutations_are_not_automatically_retried(transport: Mock, operation: str) -> None:
    client = MtnCloudClient(
        settings=ClientSettings(_env_file=None, token="unit-test", max_retries=3),
        transport=transport,
        sleeper=Mock(),
    )
    transport.request.return_value = HttpResponse(503, {}, {"message": "busy"})
    with pytest.raises(ServerError):
        invoke(client, operation)
    transport.request.assert_called_once()


@pytest.mark.parametrize(
    "model",
    [
        StorageBucketCreate(name="backup", bucket_name="backup", config=CONFIG),
        StorageBucketUpdate(config=CONFIG),
        StorageBucket(id=7, name="backup", config=CONFIG),
    ],
)
def test_provider_config_is_hidden_in_repr_but_retained_in_serialization(model: Any) -> None:
    assert "unit-secret" not in repr(model) + str(model)
    assert "unit-access" not in repr(model) + str(model)
    assert model.model_dump()["config"] == CONFIG
    if hasattr(model, "to_api_payload"):
        assert model.to_api_payload()["storageBucket"]["config"] == CONFIG


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (StorageBucket, {"config": CONFIG}),
        (StorageBucketCreate, {"config": CONFIG}),
        (StorageBucketUpdate, {"config": CONFIG, "copyToStore": "unit-secret"}),
    ],
)
def test_rendered_model_validation_errors_hide_sensitive_inputs(
    model: Any, payload: dict[str, Any]
) -> None:
    with pytest.raises(ModelValidationError) as raised:
        model.model_validate(payload)
    assert "unit-secret" not in str(raised.value)
    assert "unit-access" not in str(raised.value)
