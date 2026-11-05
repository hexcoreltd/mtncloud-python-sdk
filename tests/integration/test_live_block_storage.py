"""Opt-in read-only block-storage checks; no allocation or attachment occurs."""

import json
import os
from collections.abc import Iterator

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.volume import StorageVolume
from mtn_cloud.modern_exceptions import MtnCloudError


@pytest.fixture(scope="module")
def storage_client() -> Iterator[MtnCloudClient]:
    if os.getenv("MTN_CLOUD_RUN_LIVE_TESTS", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("set MTN_CLOUD_RUN_LIVE_TESTS=1 to run live block-storage tests")
    settings = ClientSettings(timeout=10, max_retries=0)
    if not settings.token_value():
        pytest.fail("Live block-storage tests require MTN Cloud credentials")
    with MtnCloudClient(settings=settings) as client:
        failure = None
        try:
            client.whoami()
        except MtnCloudError as exc:
            failure = (
                f"Authentication preflight failed: {type(exc).__name__}; status={exc.status_code}"
            )
        if failure is not None:
            pytest.fail(failure, pytrace=False)
        yield client


def test_live_volume_collection_envelope(storage_client: MtnCloudClient) -> None:
    body = storage_client._core.request("GET", "/storage/volumes", params={"max": 5, "offset": 0})
    if not isinstance(body, dict) or not isinstance(body.get("storageVolumes"), list):
        pytest.fail("Expected a JSON storageVolumes collection envelope", pytrace=False)
    # An empty collection verifies the envelope only, not the item contract.
    page = storage_client.volumes.list_page(limit=5)
    assert all(volume.id > 0 for volume in page.items)


def test_live_volume_detail_and_attachment_evidence(storage_client: MtnCloudClient) -> None:
    volumes = storage_client.volumes.list(limit=5)
    if not volumes:
        pytest.skip("No volumes available; detail/attachment contract was not exercised")
    body = storage_client._core.request("GET", f"/storage/volumes/{volumes[0].id}")
    if not isinstance(body, dict) or not isinstance(body.get("storageVolume"), dict):
        pytest.fail("Expected a JSON storageVolume detail envelope", pytrace=False)
    raw = body["storageVolume"]
    volume = StorageVolume.model_validate(raw)
    assert volume.id == volumes[0].id
    if "instanceId" not in raw:
        assert volume.attachment_state == "unknown"
        assert not volume.is_unattached and not volume.is_available
        pytest.skip("Detail omits instanceId; attachment ownership contract remains unverified")
    if raw["instanceId"] is None:
        assert volume.attachment_state == "unattached"
    else:
        if type(raw["instanceId"]) is not int or raw["instanceId"] <= 0:
            pytest.fail("Expected instanceId to be null or a positive integer", pytrace=False)
        assert volume.attachment_state == "attached"
        assert not volume.is_available


def test_live_volume_type_contract(storage_client: MtnCloudClient) -> None:
    types = storage_client.volumes.list_types(limit=5, enabled_only=False)
    if not types:
        pytest.skip("No volume types available; type detail contract was not exercised")
    assert storage_client.volumes.get_type(types[0].id).id == types[0].id


def test_live_volume_cli_inventory(
    storage_client: MtnCloudClient, capsys: pytest.CaptureFixture[str]
) -> None:
    from mtn_cloud.cli import main

    code = main(
        ["inventory", "--only", "volumes", "--output", "json"],
        client_factory=lambda settings: storage_client,
    )
    assert code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["schema"] == "mtncloud.inventory/v1"
    assert list(document["resources"]) == ["volumes"]
    for item in document["resources"]["volumes"]["items"]:
        assert item["attachment_state"] in {"attached", "unattached", "unknown"}
        assert not {"storage_type", "datastore", "zone"}.intersection(item)
        if item["attachment_state"] == "unknown":
            assert "instance_id" not in item
            assert item["is_available"] is False
