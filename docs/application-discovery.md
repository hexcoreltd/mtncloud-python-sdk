# Application discovery

`cloud.apps` discovers applications and catalog deployments through the
existing `/apps` control-plane collection. This is a foundation for later
managed-database workflows, not a database provisioning or management API.
An application type/category label alone does not prove managed-database
capabilities, database readiness or recoverability.

## SDK

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    app = cloud.apps.get_by_name("ledger", group_id=7)
    print(app.id, app.name, app.status)
    for application in cloud.apps.list_all(group_id=7):
        print(application.id, application.name, application.app_type)
```

Name lookup requires an exact, unique match across all pages. Misses raise
`LookupNotFoundError`; duplicates raise `AmbiguousLookupError`. `list()` still
returns a single page. Configuration stays available in SDK models and raw
serialization, which may contain secrets. Rendered model validation errors
hide input values, but structured error details can retain them.

## CLI

```bash
mtncloud apps list --group production --name ledger
mtncloud apps describe ledger --group production
mtncloud apps describe 42
mtncloud inventory --only apps --group production -o json
mtncloud inventory --only instances,apps --group production -o json
```

Application list/name lookup supports group scope. Numeric-ID describe uses
direct retrieval and ignores group scope, matching existing CLI behavior.
Zone scope is rejected before requests. Application inventory is opt-in;
default inventory remains instances, networks and routers.

CLI JSON and tables expose selected operational fields, excluding config,
description and nested group/cloud/instance metadata. Normal provider and
scope errors are sanitized without changing error types or exit codes.
Debug traces may contain original provider data. No application/database
mutations or inferred database classification are introduced.

## Pagination guarantees and limits

The shared `list_all()` adapter rejects unexpected nonempty-page offsets and
follows an explicitly reported page-size cap when no total is available. It
returns each integer resource ID once: repeated items on later pages are
dropped, and a page that adds no new IDs ends pagination. `meta.total` is a
hint, because MTN Cloud has been observed to over-report it and repeat items
at later offsets. This applies to every modern service using that adapter.

Collection traversal is not a snapshot. Concurrent resource changes can shift
items between pages, and a provider that ignores `offset` yields only its first
page. These checks do not detect every possible omission or prove that a
provider honors filters. Live validation of group filtering remains pending.

## Live verification

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_applications.py -q -x --tb=short
```

The GET-only suite checks existing details, pagination and CLI inventory.
Set `MTN_CLOUD_TEST_APP_NAME` for the optional exact-name check. Empty or
insufficient collections skip item/pagination checks without claiming coverage.
No orders or database mutations are submitted. Live verification is deferred
until authenticated control-plane access is restored.
