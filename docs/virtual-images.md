# Virtual-image discovery

`MtnCloudClient.virtual_images` provides read-only image discovery through
`/virtual-images` and `/virtual-images/{id}`. It uses the existing legacy
endpoint and the upstream Morpheus API reference. MTN-specific live
verification is pending; passing mocked tests does not establish tenant
permissions, image availability or provisioning compatibility.

## Usage

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    page = cloud.virtual_images.list_page(limit=25, image_type="qcow2")
    for image in page.items:
        print(image.id, image.name, image.image_type, image.os_name)

    # Use the scope appropriate to your tenant; omission keeps the server default.
    images = cloud.virtual_images.list_all(filter_type="Synced")
    image = cloud.virtual_images.get_by_name("AlmaLinux 10", filter_type="Synced")
    detail = cloud.virtual_images.get(image.id)
```

`list()` returns one page. `list_all()` follows offsets, returns each image
ID once and fails on offset mismatches. MTN Cloud has been observed to report a
`total` larger than the images it returns and repeating an image at a later
offset; `list_all()` drops the repeat and stops when the offset reaches
`total`. Name lookup searches all pages and requires an exact, unique name: missing matches raise `LookupNotFoundError`; duplicates
raise `AmbiguousLookupError`. Format and origin filters are retained on every
page. Permission and later-page errors propagate without returning partial
results or broadening scope. Collections are not a transactional snapshot.
The shared adapter treats `meta.size` as a page count, not a collection total;
without `meta.total`, it follows full pages until a short or empty page.

Limits must be positive integers, offsets non-negative integers and detail
IDs positive integers. Invalid inputs fail before transport. Search supports
`name`, `phrase`, `image_type` and `filter_type`; unsupported filters fail
instead of silently altering requests.

## Origin and visibility

The upstream [list API](https://apidocs.morpheusdata.com/reference/listvirtualimages)
documents `filterType` as `User`, `System`, `Synced` or `All`. These values
describe image origin; they do not select public/private visibility. The
modern service exposes this as `filter_type`, preserving case, and omits it
unless supplied. It intentionally does not copy the legacy `is_public` to
`filterType` translation. The legacy resource manager retains its existing API.

The response model keeps `visibility`, `is_public`, `system_image`,
`user_uploaded` and `user_defined` independently. Absent values remain `None`;
visibility, readiness and tenant access are not inferred from origin, image
name or location metadata. Images are separate from instance types/layouts;
an image ID alone is not a supported provisioning request.

## Metadata and sensitive data

`VirtualImage` retains OS references, sizes, location metadata, labels and
both legacy string tags and `VirtualImageTag(name=..., value=...)` tags.
Size units and provider-specific metadata still require MTN verification.
Unknown response fields, including unmodeled SSH credentials, are ignored.
Existing user-data and provider metadata remain accessible in SDK fields and
serialization. Model representations and rendered validation errors hide
these inputs; raw dumps and structured validation details can contain secrets.
The example [list_virtual_images.py](../examples/list_virtual_images.py)
prints selected scalar metadata only.

## Contract verification

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_virtual_images.py -q -x --tb=short
```

The guarded suite checks collection/detail envelopes and successive pages
using existing images. Set `MTN_CLOUD_TEST_IMAGE_NAME` for an optional unique
name lookup within the provider's default scope. Empty collections and
insufficient pagination data skip affected checks without claiming coverage.
Origin-filter behavior remains pending a dedicated live check with suitable
tenant data. No import, upload, delete, image provisioning or CLI commands
are added by this feature.
