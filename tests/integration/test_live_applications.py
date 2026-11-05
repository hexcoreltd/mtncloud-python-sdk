"""Opt-in application reads; no catalog orders or database mutations."""

import json
import os

import pytest

from mtn_cloud import MtnCloudClient


def test_live_application_collection_and_detail(authenticated_client: MtnCloudClient) -> None:
    page = authenticated_client.apps.list_page(limit=5)
    if not page.items:
        pytest.skip("No applications available; detail contract was not exercised")
    assert authenticated_client.apps.get(page.items[0].id).id == page.items[0].id


def test_live_application_pagination(authenticated_client: MtnCloudClient) -> None:
    first = authenticated_client.apps.list_page(limit=1)
    if not first.items or first.total is None or first.total < 2:
        pytest.skip("At least two applications and total metadata are needed to verify pagination")
    second = authenticated_client.apps.list_page(limit=1, offset=1)
    if not second.items:
        pytest.fail("Second application page is empty despite total metadata", pytrace=False)
    assert first.items[0].id != second.items[0].id


def test_live_application_name_lookup(authenticated_client: MtnCloudClient) -> None:
    name = os.getenv("MTN_CLOUD_TEST_APP_NAME")
    if not name:
        pytest.skip("Set MTN_CLOUD_TEST_APP_NAME to an existing unique application name")
    assert authenticated_client.apps.get_by_name(name).name == name


def test_live_application_cli_inventory(
    authenticated_client: MtnCloudClient, capsys: pytest.CaptureFixture[str]
) -> None:
    from mtn_cloud.cli import main

    assert (
        main(
            ["inventory", "--only", "apps", "-o", "json"],
            client_factory=lambda settings: authenticated_client,
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    assert document["schema"] == "mtncloud.inventory/v1"
    assert list(document["resources"]) == ["apps"]
    for item in document["resources"]["apps"]["items"]:
        assert not {"config", "instances", "group", "cloud", "description"}.intersection(item)
