# Snapshot contracts and recovery

Modern snapshot adapters follow the upstream Morpheus contract. They have
mocked regression coverage; MTN-specific live verification remains pending.
This feature corrects earlier adapters that assumed synchronous creation and
used different creation/deletion paths. Existing legacy `MTNCloud` resource
managers are unchanged and are not evidence of current contract validity.

## Discovery

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    snapshots = cloud.instances.list_snapshots(100)
    for snapshot in snapshots:
        print(snapshot.id, snapshot.name, snapshot.status)

    # Use existing IDs/names from your tenant.
    snapshot = cloud.instances.get_snapshot(100, 81)
    named = cloud.instances.get_snapshot_by_name(100, "pre-upgrade")
    detail = cloud.snapshots.get(snapshot.id)
```

`list_snapshots` reads the instance collection. The upstream contract declares
no pagination/filter parameters, so the SDK does not invent them. Scoped ID
and name lookup require unique matches; missing matches raise
`LookupNotFoundError`, duplicates `AmbiguousLookupError`. An explicit
conflicting instance reference is rejected. Missing parent metadata remains
unknown; collection membership is evidence from the scoped endpoint, not an
independent ownership assertion.

`cloud.snapshots.get(id)` retrieves global snapshot detail and checks that the
returned ID matches the request. IDs must be positive integers. Models accept
upstream string/null `state` and `datastore` alongside legacy dictionary
values. They retain `currentlyActive`, snapshot flags, storage size, parent
reference and file metadata. Missing status/flags stay unknown; no readiness
or recovery-success classification is inferred.

## Asynchronous creation: compatibility change

`instances.create_snapshot(instance_id, SnapshotCreate(...))` now performs
`PUT /instances/{id}/snapshot` and returns `SnapshotSubmission`:

```python
from mtn_cloud import MtnCloudClient
from mtn_cloud.models import SnapshotCreate

# MUTATING: run deliberately against a supported instance after MTN verification.
with MtnCloudClient() as cloud:
    submission = cloud.instances.create_snapshot(
        100, SnapshotCreate(name="pre-upgrade", memory_snapshot=False, for_export=False)
    )
    print(submission.instance_id, submission.process_ids)
```

This replaces the earlier POST adapter and `Snapshot` return value. Replace
uses of `created.id` with submission tracking and later snapshot discovery.
Process IDs identify operations, not snapshots; never pass them to snapshot
deletion or restore. Multiple processes can correspond to an instance with
multiple servers. An empty process list supplies no tracking identifiers.

Only explicit boolean `success: true` is accepted. Missing or malformed
process-ID data raises an SDK error with the instance ID in
`error.response["instance_id"]`. Inspect the instance before resubmitting;
an invalid response does not establish that the mutation failed. The SDK
does not automatically retry submissions or poll guessed completion states.
Read-only process inspection and caller-configured status polling are now
available through `cloud.processes`; see the [process guide](processes.md).
MTN status semantics and verified snapshot-completion policies remain pending.

`SnapshotCreate` retains name/description and adds optional `memory_snapshot`
and `for_export` flags. Explicit false values are preserved. Provider support
for those options still requires MTN verification.

## Provider support

Live runs on 2026-11-05 showed that MTN Cloud decides snapshot support per
instance type. `create_snapshot` on an `MTN-U24.04LTS` instance returned HTTP
400 with "Instance type does not support snapshots", raised as the SDK's
`ValidationError`. Neither instance types nor layouts expose a snapshot
capability field to tenant credentials, so support cannot be checked before
submitting. The guarded lifecycle test in
`tests/integration/test_live_snapshot_lifecycle.py` skips with that reason
when the selected type refuses snapshots; set
`MTN_CLOUD_TEST_INSTANCE_TYPE_CODE` to a snapshot-capable type to exercise
creation, process tracking, restore and deletion.

## Restore and deletion

`instances.revert_snapshot(instance_id, snapshot_id)` checks the instance
collection before submitting the existing PUT restore action.
`instances.delete_snapshot(instance_id, snapshot_id)` performs the same
membership check, then deletes through `/snapshots/{snapshot_id}`. Missing,
duplicate or conflicting membership prevents the write. This introduces a
read permission requirement and an extra GET. The check and mutation are not
atomic; a provider-side change can still occur between them.

`snapshots.delete(snapshot_id)` deliberately targets a global snapshot ID
without an instance check. Both deletion variants and restore return true
only on explicit boolean acknowledgement. Empty, malformed and explicit
failed responses raise an SDK error. True means submission acknowledged;
it does not prove deletion, restored data consistency or application readiness.
404 and permission errors propagate, and writes are not automatically retried.
Restore is destructive to later changes and needs an independently tested
recovery procedure. No restore or deletion was run during this implementation.

## Verification and sources

The contract reference is HPE's
[OpenAPI specification at revision cec1593](https://github.com/HewlettPackard/morpheus-openapi/tree/cec1593e56d04d0515ffa904b1da9f7c56e9f007).
Relevant paths are
[instance snapshot creation](https://github.com/HewlettPackard/morpheus-openapi/blob/cec1593e56d04d0515ffa904b1da9f7c56e9f007/paths/api%40instances%40id%40snapshot.yaml),
[instance collection](https://github.com/HewlettPackard/morpheus-openapi/blob/cec1593e56d04d0515ffa904b1da9f7c56e9f007/paths/api%40instances%40id%40snapshots.yaml)
and [global detail/deletion](https://github.com/HewlettPackard/morpheus-openapi/blob/cec1593e56d04d0515ffa904b1da9f7c56e9f007/paths/api%40snapshots%40id.yaml).
Upstream documentation establishes the implementation reference, not MTN
tenant permissions, enabled provider capabilities or completed live validation.

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 MTN_CLOUD_TEST_INSTANCE_ID=100 \
  uv run pytest tests/integration/test_live_snapshots.py -q -x --tb=short
```

Use an existing instance ID. Optionally set `MTN_CLOUD_TEST_SNAPSHOT_NAME`
for exact-name lookup. The guarded suite performs GET requests only. Missing
configuration or empty collections skip relevant checks without claiming
detail or lifecycle coverage. Mutation tests are deferred until submission
tracking, provider capabilities and cleanup can be verified safely.

Snapshot files, descriptions, state and datastore data can contain sensitive
metadata. Model representations omit metadata and rendered validation errors
hide input values. Raw serialization and structured validation details remain sensitive. The
[read-only example](../examples/list_snapshots.py) prints selected fields.
