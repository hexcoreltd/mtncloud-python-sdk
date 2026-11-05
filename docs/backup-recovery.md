# Backup discovery and execution submissions

The modern `cloud.backups` service inspects existing configurations, job
definitions and execution results. Full recovery workflows, restore testing,
scheduling mutations and retention management remain pending.

## Read configurations and history

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    for backup in cloud.backups.list_all():
        print(backup.id, backup.name, backup.last_status)
        results = cloud.backups.list_all_results(backup.id, page_size=50)
        for result in results:
            print(result.id, result.status, result.start_date, result.end_date)

    for job in cloud.backups.list_all_jobs(page_size=50):
        print(job.id, job.name, job.cron_expression)
```

`list_results()` and `list_jobs()` remain single-page operations. For explicit
page control, use `list_results_page(backup_id, limit=50, offset=0)` and
`list_jobs_page(limit=50, offset=0)`. Both return typed `Page` objects containing
`items`, `offset`, `limit` and `total`.

All-page methods use the existing collection adapter and propagate API failures
instead of returning a partial history after an error. Pagination is not a
transactional snapshot; records can change during traversal. Provider support
for result offsets and metadata interpretation still needs live verification.
An explicitly mismatched `backupId` in a result fails parent validation;
missing parent metadata is accepted without claiming ownership is verified.

## Read-only CLI

```bash
mtncloud backups list --name nightly -o json
mtncloud backups describe nightly
mtncloud backups jobs -o json
mtncloud backups results 42 -o json
mtncloud inventory --only instances,backups -o json
```

Configuration names are matched exactly by `describe` across all pages.
`list --name` uses the API's phrase search. Missing names exit 4 and ambiguous
names exit 5. The SDK also exposes `cloud.backups.get_by_name(name)` with typed
lookup errors.

Jobs and results use `mtncloud.list/v1` envelopes with resource names
`backup-jobs` and `backup-results`. Result output additionally includes a
top-level `backup_id`: the requested configuration ID, not fabricated parent
metadata on result items. Results require a positive numeric ID and preserve
provider status strings. JSON and table outputs exclude raw error messages,
result configuration and nested provider metadata.

Group/zone scope is unsupported and fails with exit code 2 before requests.
Configuration inventory is opt-in through `--only backups`; jobs and results
are not inventory sections. Default inventory remains instances, networks
and routers. Normal errors preserve exit codes and operation metadata while
using generic messages. Debug traces may contain original provider details.

There are no CLI execute, delete, or restore commands in this increment.

## Submit executions deliberately

`execute(backup_id)` and `execute_job(job_id)` perform POST requests and return
the provider's submission object. They are never automatically retried. An
explicit `success: false` raises `MtnCloudError`; an accepted response does
not establish that backup data was created, is usable, or can be restored.
Status strings remain provider values until lifecycle transitions are verified.
The SDK does not introduce completion waiters based on guessed statuses.

`delete(backup_id)` targets a backup configuration and rejects an explicit
failed response. Its effect on schedules, retained artifacts and provider
data must be established before using it in recovery automation.

Provider execution responses, result configuration and error details may
contain sensitive data; the example prints only selected operational fields.

## Verification status

Mocked tests cover pagination, failed envelopes, parent references, invalid
arguments, error propagation, and single-attempt mutations. Shared collection
and detail adapters reject explicit failed envelopes before parsing. Page
metadata retains a reported zero total and uses request values when offset or
limit metadata is absent.

Prepared live checks use only GET requests:

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_backups.py -q -x --tb=short
```

They verify existing configuration/job details, result items and offset
pagination when the tenant has enough records. Missing test data skips the
corresponding checks; permission and connection errors fail the run. No live
execution, deletion or restore is performed. Live contract verification is
deferred until control-plane access is restored.
