# Process history and explicit status polling

`cloud.processes` exposes read-only operation records through the upstream
Morpheus history API. It lets callers inspect process IDs returned by
asynchronous snapshot submission. MTN live validation remains pending.

## Inspect existing operations

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    process = cloud.processes.get(901)
    print(process.id, process.status, process.percent)

    # Requires the response to explicitly identify this instance.
    process = cloud.processes.get(901, instance_id=100)

    page = cloud.processes.list_page(instance_id=100)
    for process in page.items:
        print(process.id, process.status)
    print(page.offset, page.limit, page.total)
```

Replace IDs with existing tenant resources. Detail lookup rejects a mismatched
process ID. When `instance_id` is supplied, a missing or conflicting instance
reference is rejected. Embedded events must not explicitly reference another
process; omitted event parent metadata remains unknown.

History supports `instance_id`, `container_id`, `server_id`, `zone_id`,
`app_id` and `phrase`. Reference filters require positive integer IDs.
Explicit conflicting instance references fail collection parsing; omitted
references remain unknown, so filtering alone does not establish ownership.

`list()` returns the provider-selected page's items. `list_page()` additionally
preserves response metadata. The upstream specification declares history
metadata but no paging query parameters. There are therefore no `limit`,
`offset` or `list_all` controls in this service. A page may report more items
than it contains; do not treat either method as a complete history export.
Paging controls require separate MTN contract verification.

## Track a snapshot submission

Use the `SnapshotSubmission` already returned by deliberate snapshot creation:

```python
with MtnCloudClient() as cloud:
    for process_id in submission.process_ids:
        process = cloud.processes.get(process_id, instance_id=submission.instance_id)
        print(process.id, process.status)
```

Process IDs identify operations. Result type/ID, percentage, timestamps and
status remain provider data; none is automatically converted into a snapshot
ID, readiness result or recovery guarantee. An empty submission process list
supplies no tracking IDs. This feature does not create or restore snapshots.

## Poll for a caller-selected status

```python
with MtnCloudClient() as cloud:
    # Choose labels established for your tenant and operation type.
    process = cloud.processes.wait_for_status(
        901,
        "complete",
        instance_id=100,
        failure_statuses={"failed"},
        timeout=300,
        poll_interval=5,
    )
```

The example labels are illustrative. The SDK has no implicit success/failure
mapping. Matching ignores case and outer spaces. Unknown or absent statuses
continue polling; percentage 100 is not a completion condition. A caller may
choose any target, including a failure label, when inspecting that transition.
Target and failure sets must not overlap. Caller-designated failures raise
`MtnCloudError`; timeout raises the modern `TimeoutError`. Their response
context includes process ID and last observed status, excluding process logs.

`timeout` and `poll_interval` must be finite and positive. The monotonic
polling budget caps sleeps and prevents another polling attempt at the deadline.
It is checked between requests: HTTP timeouts, core GET retries and callbacks
can extend wall-clock duration. A matching response that arrives after a slow
request can still be returned. Configure the client's request timeout and
retry policy for the environment's timing requirements.

Optional `on_status(process)` receives each observation. Callback exceptions
propagate. Callback changes to status do not determine polling decisions.
Authentication, permission, connection and not-found errors propagate rather
than becoming successful completion. No process retry/cancel mutation is
exposed. A matching status still requires independent resource and recovery
verification; automatic snapshot completion policies remain pending.

## Sensitive data and models

`Process` and `ProcessEvent` retain messages, output, errors, reasons, actors
and nested event data. Representations show only record type and ID. Rendered
model-validation errors hide inputs, but serialization, structured validation
details and original exception causes can retain sensitive data. Print selected
operational fields instead of raw models or dumps. Provider text, including log
whitespace, is preserved; status normalization applies only to comparisons. The
[read-only example](../examples/process_history.py) follows this pattern.

## Verification and contract reference

Implementation follows HPE's pinned OpenAPI
[history collection](https://github.com/HewlettPackard/morpheus-openapi/blob/cec1593e56d04d0515ffa904b1da9f7c56e9f007/paths/api%40processes.yaml),
[process detail](https://github.com/HewlettPackard/morpheus-openapi/blob/cec1593e56d04d0515ffa904b1da9f7c56e9f007/paths/api%40processes%40id.yaml)
and [process schema](https://github.com/HewlettPackard/morpheus-openapi/blob/cec1593e56d04d0515ffa904b1da9f7c56e9f007/components/schemas/process.yaml).
Status semantics, filtering, pagination and tenant permissions still need MTN
verification. Passing mocked tests does not establish these live contracts.

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_processes.py -q -x --tb=short
```

Set `MTN_CLOUD_TEST_PROCESS_ID` for an existing process detail check and
optionally `MTN_CLOUD_TEST_INSTANCE_ID` for instance binding/filter checks.
Missing selectors or insufficient data skip corresponding checks without
claiming coverage. The prepared suite performs GET requests only and neither
polls toward an assumed status nor creates, retries or cancels operations.
