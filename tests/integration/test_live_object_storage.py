"""Opt-in storage configuration reads, without bucket or object mutations."""

import json

import pytest

from mtn_cloud import MtnCloudClient


def test_live_storage_bucket_collection_envelope(storage_client: MtnCloudClient) -> None:
    body = storage_client._core.request("GET", "/storage-buckets", params={"max": 5, "offset": 0})
    if not isinstance(body, dict) or not isinstance(body.get("storageBuckets"), list):
        pytest.fail("Expected a JSON storageBuckets collection envelope", pytrace=False)
    page = storage_client.storage_buckets.list_page(limit=5)
    assert all(bucket.id > 0 for bucket in page.items)


def test_live_storage_bucket_detail(storage_client: MtnCloudClient) -> None:
    buckets = storage_client.storage_buckets.list(limit=5)
    if not buckets:
        pytest.skip("No configurations available; bucket detail contract was not exercised")
    bucket = storage_client.storage_buckets.get(buckets[0].id)
    assert bucket.id == buckets[0].id
    # Do not print or persist provider config: it can carry access credentials.
    if bucket.config is not None:
        assert isinstance(bucket.config, dict)


def test_live_storage_bucket_pagination(storage_client: MtnCloudClient) -> None:
    first_page = storage_client.storage_buckets.list_page(limit=1)
    if first_page.total is None or first_page.total < 2 or not first_page.items:
        pytest.skip(
            "At least two configurations and total metadata are needed to verify pagination"
        )
    second_page = storage_client.storage_buckets.list_page(limit=1, offset=1)
    if not second_page.items:
        pytest.fail(
            "Second page is empty despite total metadata reporting more items", pytrace=False
        )
    assert first_page.items[0].id != second_page.items[0].id


def test_live_storage_bucket_cli_inventory(
    storage_client: MtnCloudClient, capsys: pytest.CaptureFixture[str]
) -> None:
    from mtn_cloud.cli import main

    code = main(
        ["inventory", "--only", "storage-buckets", "--output", "json"],
        client_factory=lambda settings: storage_client,
    )
    assert code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["schema"] == "mtncloud.inventory/v1"
    assert list(document["resources"]) == ["storage-buckets"]
    section = document["resources"]["storage-buckets"]
    assert section["count"] == len(section["items"])
    for item in section["items"]:
        assert "id" in item
        assert not {"config", "storage_server", "account_id", "retention_provider"}.intersection(
            item
        )
