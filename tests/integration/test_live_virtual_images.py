"""Opt-in GET-only image checks; no import, upload, provisioning or deletion."""

import os

import pytest

from mtn_cloud import MtnCloudClient


def test_live_image_collection_envelope(authenticated_client: MtnCloudClient) -> None:
    body = authenticated_client._core.request("GET", "/virtual-images", params={"max": 5})
    if not isinstance(body, dict) or not isinstance(body.get("virtualImages"), list):
        pytest.fail("Expected a JSON virtualImages collection envelope", pytrace=False)
    page = authenticated_client.virtual_images.list_page(limit=5)
    assert all(image.id > 0 for image in page.items)


def test_live_image_detail(authenticated_client: MtnCloudClient) -> None:
    images = authenticated_client.virtual_images.list(limit=5)
    if not images:
        pytest.skip("No images available; detail/metadata contract was not exercised")
    body = authenticated_client._core.request("GET", f"/virtual-images/{images[0].id}")
    if not isinstance(body, dict) or not isinstance(body.get("virtualImage"), dict):
        pytest.fail("Expected a JSON virtualImage detail envelope", pytrace=False)
    detail = authenticated_client.virtual_images.get(images[0].id)
    assert detail.id == images[0].id


def test_live_image_pagination(authenticated_client: MtnCloudClient) -> None:
    first = authenticated_client.virtual_images.list_page(limit=1)
    if not first.items or first.total is None or first.total < 2:
        pytest.skip("At least two images and total metadata are needed to verify pagination")
    # MTN Cloud can over-report `total` and repeat an image at a later offset
    # (observed 2026-11-05), so assert the adapter's guarantee, not distinct pages.
    images = authenticated_client.virtual_images.list_all(page_size=1)
    ids = [image.id for image in images]
    assert ids, "Paged traversal returned no images despite total metadata"
    assert len(ids) == len(set(ids))
    assert len(ids) <= first.total
    assert first.items[0].id in ids


def test_live_image_exact_name(authenticated_client: MtnCloudClient) -> None:
    name = os.getenv("MTN_CLOUD_TEST_IMAGE_NAME")
    if not name:
        pytest.skip("Set MTN_CLOUD_TEST_IMAGE_NAME to a unique image in the default scope")
    assert authenticated_client.virtual_images.get_by_name(name).name == name
