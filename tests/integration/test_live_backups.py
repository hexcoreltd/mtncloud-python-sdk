"""Opt-in backup discovery checks; never execute or delete a backup."""

import pytest

from mtn_cloud import MtnCloudClient


def test_live_backup_collection_and_detail(storage_client: MtnCloudClient) -> None:
    page = storage_client.backups.list_page(limit=5)
    if not page.items:
        pytest.skip("No backups available; backup detail contract was not exercised")
    assert storage_client.backups.get(page.items[0].id).id == page.items[0].id


def test_live_backup_result_collection(storage_client: MtnCloudClient) -> None:
    backups = storage_client.backups.list(limit=5)
    if not backups:
        pytest.skip("No backup available; result contract was not exercised")
    page = storage_client.backups.list_results_page(backups[0].id, limit=5)
    if not page.items:
        pytest.skip("No execution results available; result item contract was not exercised")
    assert all(result.id > 0 for result in page.items)
    assert all(result.backup_id in (None, backups[0].id) for result in page.items)


def test_live_backup_job_detail(storage_client: MtnCloudClient) -> None:
    page = storage_client.backups.list_jobs_page(limit=5)
    if not page.items:
        pytest.skip("No backup jobs available; job detail contract was not exercised")
    assert storage_client.backups.get_job(page.items[0].id).id == page.items[0].id


@pytest.mark.parametrize("kind", ["results", "jobs"])
def test_live_backup_pagination(storage_client: MtnCloudClient, kind: str) -> None:
    backup_id = None
    if kind == "results":
        backups = storage_client.backups.list(limit=1)
        if not backups:
            pytest.skip("No backup available for result pagination")
        backup_id = backups[0].id
        first = storage_client.backups.list_results_page(backup_id, limit=1)
    else:
        first = storage_client.backups.list_jobs_page(limit=1)
    if not first.items or first.total is None or first.total < 2:
        pytest.skip("At least two items and total metadata are needed to verify pagination")
    second = (
        storage_client.backups.list_results_page(backup_id, limit=1, offset=1)
        if backup_id is not None
        else storage_client.backups.list_jobs_page(limit=1, offset=1)
    )
    if not second.items:
        pytest.fail(
            "Second page is empty despite total metadata reporting more items", pytrace=False
        )
    assert first.items[0].id != second.items[0].id
