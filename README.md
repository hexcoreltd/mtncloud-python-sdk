# MTN Cloud Python SDK

![Python](https://img.shields.io/badge/python-%3E%3D3.10-3776AB?logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-2ea44f)
![License](https://img.shields.io/badge/license-MIT-green)

A typed, synchronous Python SDK for the [MTN Cloud Console API](https://console.cloud.mtn.ng/documentation/).
The package is published as `mtncloud-python-sdk` and imported in Python as
`mtn_cloud`.

This unofficial SDK is maintained by [Hexcore Ltd](https://github.com/hexcoreltd),
a Nigerian technology consulting company focused on cloud infrastructure,
automation, and migration engineering.
It provides a small, explicit client for tenant discovery, compute instance
management, networking, security groups, and long-running provisioning
operations.

> **Project status:** version `0.1.0` is the first modernized release. The
> modern client is usable for the currently verified API surface, but the
> package is still expanding toward complete MTN Cloud API coverage. The
> legacy client remains available for compatibility while services are migrated.

## What this SDK provides

- Environment-based and explicit credential configuration
- Bearer-token authentication with secrets represented as `SecretStr`
- A reusable HTTP transport with timeout, retry, and typed error handling
- Pydantic models for API responses and request payloads
- Tenant-aware discovery of groups, zones, instance types, plans, and resource pools
- Context-aware instance provisioning that resolves compatible placement dependencies
- Network discovery and subnet lookup
- Security-group and firewall-rule management
- Instance lifecycle actions: start, stop, restart, and suspend
- Polling waiters for provisioning, running, stopped, and deleted states
- Explicit dry-run support for safe provisioning previews
- Unit tests and opt-in live contract tests with mutation safeguards

## Requirements

- Python 3.10 or newer
- An MTN Cloud API credential with access to the API operations you intend to use
- [`uv`](https://docs.astral.sh/uv/) is recommended for development and reproducible environments

## Installation

Install the published package with `uv`:

```bash
uv add mtncloud-python-sdk
```

Or with pip:

```bash
python -m pip install mtncloud-python-sdk
```

For a checkout of this repository, install the development dependencies with:

```bash
uv sync --extra dev
```

## Authentication and configuration

The client reads settings from environment variables prefixed with
`MTN_CLOUD_`. A `.env` file in the working directory is also supported. Do not
commit credentials or include them in issue reports.

The preferred environment variable is `MTN_CLOUD_TOKEN`. The compatible
`MTN_CLOUD_API_KEY` variable is also accepted. `MTN_CLOUD_API_REFRESH_TOKEN`
is retained as configuration for future token refresh support; the current
verified API flow uses the access token/API key value.

```bash
export MTN_CLOUD_TOKEN="your-api-token"
```

For local development, create `.env`:

```dotenv
MTN_CLOUD_TOKEN=your-api-token
MTN_CLOUD_BASE_URL=https://console.cloud.mtn.ng
MTN_CLOUD_TIMEOUT=30
MTN_CLOUD_MAX_RETRIES=3
```

Supported settings include:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `MTN_CLOUD_BASE_URL` | `https://console.cloud.mtn.ng` | MTN Cloud control-plane host |
| `MTN_CLOUD_API_PREFIX` | `/api` | API path prefix |
| `MTN_CLOUD_TOKEN` | unset | Bearer access token |
| `MTN_CLOUD_API_KEY` | unset | Compatibility credential name |
| `MTN_CLOUD_API_REFRESH_TOKEN` | unset | Refresh-token configuration |
| `MTN_CLOUD_TIMEOUT` | `30` | Per-request timeout in seconds |
| `MTN_CLOUD_MAX_RETRIES` | `3` | Retries for retryable idempotent requests |
| `MTN_CLOUD_RETRY_DELAY` | `0.5` | Base retry delay in seconds |
| `MTN_CLOUD_VERIFY_SSL` | `true` | TLS certificate verification |
| `MTN_CLOUD_USER_AGENT` | `mtncloud-python-sdk/0.1.0` | HTTP user-agent value |

Explicit constructor values take precedence over environment values:

```python
from mtn_cloud import ClientSettings, MtnCloudClient

settings = ClientSettings(
    token="your-api-token",
    timeout=45,
    max_retries=3,
)

with MtnCloudClient(settings=settings) as cloud:
    print(cloud.ping())
```

For simple scripts, passing a token directly is also supported:

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient(token="your-api-token") as cloud:
    user = cloud.whoami()
    print(user)
```

## Basic discovery

Services are exposed as lazy client properties. Responses are validated into
typed Pydantic models.

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    groups = cloud.groups.list()
    instance_types = cloud.instance_types.list()
    networks = cloud.networks.list()

    for group in groups:
        print(group.id, group.name)

    for instance_type in instance_types:
        print(instance_type.code, instance_type.name)

    for network in networks:
        print(network.id, network.name, network.cidr)
```

The current modern service surface is:

| Service | Main operations |
| --- | --- |
| `cloud.zones` | List and retrieve deployment zones |
| `cloud.groups` | List and retrieve tenant groups/projects |
| `cloud.instance_types` | Discover instance types and layouts |
| `cloud.plans` | List general and provisioning-scoped service plans |
| `cloud.resource_pools` | Discover compatible placement pools |
| `cloud.instances` | List, create, update, delete, and operate instances |
| `cloud.networks` | List, create, update, and delete networks; list subnets |
| `cloud.routers` | Discover external gateways and manage MTN routers |
| `cloud.security_groups` | Manage security groups and firewall rules |
| `cloud.backups` | Inspect backup configurations, jobs, and results |
| `cloud.snapshots` | Retrieve/delete snapshots by global ID (MTN live verification pending) |
| `cloud.processes` | Inspect operation history/detail and poll for caller-selected statuses (MTN live verification pending) |
| `cloud.volumes` | Discover block-storage volumes, attachments, and volume types |
| `cloud.virtual_images` | Discover image metadata with pagination and exact-name lookup (live verification pending) |
| `cloud.storage_buckets` | Manage S3-compatible storage-provider configurations |
| `cloud.apps` | Discover provisioned applications and catalog deployments |

Runnable examples are available in [`examples/`](examples/), with a guide in
[`examples/README.md`](examples/README.md). Mutating examples default to safe
resolution or require an explicit `--apply` flag.

Some MTN Cloud endpoints are permission-scoped. A valid credential may be
able to access tenant-scoped endpoints while receiving `403 Forbidden` from
broader catalog endpoints. The SDK surfaces these responses as typed errors;
it does not silently broaden permissions or substitute data.

Virtual-image discovery uses the legacy endpoint and upstream reference;
MTN-specific live validation remains pending. See the
[virtual-image guide](docs/virtual-images.md) for filters, metadata handling
and prepared read-only contract checks.

Snapshot creation now returns `SnapshotSubmission` with process IDs rather
than a snapshot resource. Instance-scoped restore/deletion checks collection
membership before writing. See the [snapshot migration guide](docs/snapshots.md)
for the corrected paths, return-type change and pending MTN verification.

Use `cloud.processes.get(process_id, instance_id=...)` to inspect submitted
operation IDs. History is a provider-selected page; status polling requires
caller-selected labels and does not infer snapshot readiness. See the
[process guide](docs/processes.md) for scope checks, timing and live-test status.

### Validate network creation

Use explicit placement IDs and an OpenStack network type when checking a
network request before creation:

```python
from mtn_cloud import MtnCloudClient
from mtn_cloud.models.network import NetworkCreate

request = NetworkCreate(
    name="app-private",
    group_id=621,
    cloud_id=4,
    type_id=10,
    resource_pool_id=214,
    cidr="10.20.0.0/24",
    gateway="10.20.0.1",
)
with MtnCloudClient() as cloud:
    cloud.networks.validate_create(request)  # GET requests only; creates nothing
    # To validate and then create in one call:
    # network = cloud.networks.create(request, validate=True)
```

Replace the sample IDs with discovered tenant values. Validation checks local
address inputs, group/zone association, zone availability, network-type
creatability and resource-pool membership. It requires access to the relevant
discovery endpoints; permission failures propagate. It does not reserve the
network, check address conflicts in the provider, or guarantee creation will
succeed. Plain `create(request)` retains its existing behavior. This preflight
has mocked regression coverage; live validation is pending service recovery.

## Provision an instance safely

The high-level `provision` workflow resolves the group, zone, instance type,
layout, resource pool, and provisioning-compatible service plan before making
the create request. When a network is supplied, it validates that the network
belongs to the selected zone, group, and resource pool.

Use `dry_run=True` to inspect the resolved request without creating anything:

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    resolved = cloud.instances.provision(
        "web-01",
        type_code="MTN-AL10",
        group="MTNNG_CLOUD_AZ_1",
        plan="G1S1",
        network_id=660,
        external_network_id="public-network-01",
        root_volume_size_gb=10,
        dry_run=True,
    )
    print(resolved)
```

To create and wait for the instance to become available:

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    instance = cloud.instances.provision(
        "web-01",
        type_code="MTN-AL10",
        group="MTNNG_CLOUD_AZ_1",
        plan="G1S1",
        network_id=660,
        external_network_id="public-network-01",
        root_volume_size_gb=10,
        timeout=1_800,
        poll_interval=15,
        progress_callback=lambda item: print(item.status),
    )
    print(instance.id, instance.status)
```

Provisioning can take several minutes. Treat `timeout` as the total wait
budget, and always add cleanup handling to automation that creates resources.

## Instance lifecycle and cleanup

```python
with MtnCloudClient() as cloud:
    cloud.instances.stop(instance_id)
    stopped = cloud.instances.wait_until_stopped(instance_id, timeout=600)

    cloud.instances.start(instance_id)
    running = cloud.instances.wait_until_running(instance_id, timeout=600)

    cloud.instances.delete(instance_id)
    cloud.instances.wait_until_deleted(instance_id, timeout=600)
```

Deletion is a real cloud mutation. Use `force=True` and
`preserve_volumes=True` only when their consequences are understood.

## Security groups and rules

```python
from mtn_cloud import MtnCloudClient
from mtn_cloud.models.security_group import SecurityGroupCreate, SecurityGroupRuleCreate

with MtnCloudClient() as cloud:
    security_group = cloud.security_groups.create(
        SecurityGroupCreate(
            name="web-servers",
            description="Web workload firewall",
        )
    )
    cloud.security_groups.create_rule(
        security_group.id,
        SecurityGroupRuleCreate(
            name="allow-https",
            direction="ingress",
            protocol="tcp",
            port_range="443",
            source_type="cidr",
            source="0.0.0.0/0",
        ),
    )
```

Review the MTN Cloud tenant permissions and API behavior before using
security-group mutations in production.

## Command-line interface

The package ships a read-only `mtncloud` command for scripts, CI jobs and
operators. It needs the optional `cli` extra, which adds Typer:

```bash
python -m pip install "mtncloud-python-sdk[cli]"
# or as an isolated tool
pipx install "mtncloud-python-sdk[cli]"
uv tool install "mtncloud-python-sdk[cli]"
```

Without the extra, `mtncloud` prints an install hint to stderr and exits with
code 2. Credentials come only from `MTN_CLOUD_TOKEN` (or
`MTN_CLOUD_API_KEY`) or a `.env` file in the working directory. No option
accepts a credential.

```bash
mtncloud instances list --group production --zone lagos-1
mtncloud networks describe app-network --group production
mtncloud inventory --only instances,routers -o json > inventory.json
mtncloud volumes list --zone lagos-1
mtncloud volumes describe app-data --zone lagos-1
mtncloud inventory --only instances,volumes --zone lagos-1 -o json
mtncloud storage-buckets list --name backups
mtncloud storage-buckets describe backups
mtncloud inventory --only storage-buckets -o json
mtncloud backups list --name nightly
mtncloud backups describe nightly
mtncloud backups jobs
mtncloud backups results 42
mtncloud inventory --only backups -o json
mtncloud apps list --group production
mtncloud apps describe ledger --group production
mtncloud inventory --only apps --group production -o json
mtncloud plan --name api-01 --type-code MTN-CS10 --group production --plan G1S1 -o json
mtncloud version
```

- `mtncloud instances|networks|routers list [--group] [--zone] [--name]`
- `mtncloud volumes list [--zone] [--name]`
- `mtncloud storage-buckets list [--name]`
- `mtncloud backups list [--name]`
- `mtncloud apps list [--group] [--name]`
- `mtncloud backups jobs [-o json|table]`
- `mtncloud backups results BACKUP_ID [-o json|table]`
- `mtncloud <resource> describe <id-or-name> [--group] [--zone]`. An argument
  made only of digits is an ID and ignores `--group` and `--zone`. Anything
  else must match one name exactly. `list --name` instead passes the name to
  the API filter, which may match partially, while `describe` requires an
  exact match.
- `mtncloud inventory [--only R1,R2] [--group] [--zone]`
- `mtncloud plan --name NAME --type-code CODE --group GROUP --plan PLAN`
- `mtncloud version`

Volume commands support zone scope only. `--group` is rejected with exit code
2 before discovery, including on an inventory selection containing volumes.
For numeric volume IDs, `--zone` is ignored, as with other describe commands.
Volume `list --name` uses the API's broader `phrase` search; `describe` by
name requires an exact, unique match across all pages.

Default inventory remains `instances`, `networks`, and `routers`. Include
volumes explicitly with `--only volumes` or a mixed selection such as
`--only instances,volumes`. Volume JSON includes `attachment_state`,
`is_unattached`, and the `is_available` hint. Omitted attachment fields remain
omitted; explicit null values are preserved. Nested provider metadata
(`storage_type`, `datastore`, and `zone`) is excluded from CLI output.

Storage-bucket commands list and describe control-plane configurations by ID
or exact name. They accept neither `--group` nor `--zone`; unsupported scope
flags fail with exit code 2 before requests, including mixed inventory
selections. Include them explicitly using `--only storage-buckets` or, without
scope flags, `--only instances,volumes,storage-buckets`. Default inventory
sections remain unchanged.

Bucket JSON and tables expose operational scalar fields only. Provider
`config`, storage-server metadata and unrecognized response fields are not
included. Normal bucket error output uses a generic message while retaining
the error type, HTTP status, request ID and exit code; SDK exception objects
are not modified. `--debug` can still expose original error causes and must
be handled as sensitive output. Object transfer and bucket mutations are
not exposed by these CLI commands. Live validation remains pending.

Backup configuration list/describe uses all pages and supports unique exact
name lookup. `list --name` maps to the API's broader `phrase` filter. `jobs`
lists job definitions; `results` lists execution history for a positive numeric
configuration ID. These commands reject group/zone scope. Opt-in inventory via
`--only backups` includes configurations only; job definitions and result
history use their dedicated commands. Default inventory remains unchanged.

Backup output excludes nested provider metadata, result `config`, and raw
`error_message` fields. Normal SDK errors use generic messages while retaining
types, operation metadata and exit codes; debug tracebacks remain sensitive.
See the [backup guide](docs/backup-recovery.md) for the output contract and
verification limits.

Applications support group-scoped list/name lookup and opt-in inventory via
`--only apps`. Zone scope is rejected. Numeric-ID describes use direct reads
and ignore group scope. CLI output excludes application configuration,
description and nested resource metadata. This is application discovery;
managed-database provisioning and lifecycle workflows remain pending. See
the [application guide](docs/application-discovery.md).

Global options are `-o/--output json|table`, `--base-url`, `--timeout` and
`--debug`. `-o` may go before the command or after it, and the value after the
command wins. Running `mtncloud` with no arguments, or `mtncloud <resource>`
with no subcommand, prints help on stdout and exits 0.

An unexpected error is reported as `InternalError` with a generic message and
exit code 1. Rerun with `--debug` for details. `--debug` prints a traceback
that may include API response data, so don't share its output publicly.

The default format is `table` when stdout is a terminal and `json` when it is
piped. Table cells are rendered literally. Instance and network `config`
fields are excluded from output. Every command writes only its result to
stdout. Diagnostics and errors go to stderr, and a failed command leaves
stdout empty.

JSON documents carry a versioned `schema`: `mtncloud.list/v1`,
`mtncloud.describe/v1`, `mtncloud.inventory/v1`, `mtncloud.plan/v1`, `mtncloud.version/v1`, and
`mtncloud.error/v1` for errors on stderr. Within a version, fields may be
added but not removed or renamed.

```json
{
  "schema": "mtncloud.list/v1",
  "resource": "routers",
  "count": 1,
  "items": [{"id": 7, "name": "edge-router"}]
}
```

`inventory` exits 0 when every section succeeds. If some sections fail, it
exits 3 and prints the full document, with an `{"error": {...}}` entry in each
failed section. If every section fails, stdout is empty and the first
failure's error goes to stderr. A `--group` or `--zone` value that cannot be
resolved fails the whole command.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Internal error |
| 2 | Usage error, or the `[cli]` extra is not installed |
| 3 | Partial result (`inventory` with some failed sections) |
| 4 | Not found |
| 5 | Ambiguous name (several matches) |
| 6 | Authentication or permission, including missing credentials |
| 7 | API or network failure |
| 130 | Interrupted |

Closing a pipe early, for example `mtncloud instances list | head`, exits 0
quietly.

`plan` performs discovery only through the existing SDK dry-run resolver. It
outputs selected placement identifiers and requested options, excluding raw
provider configuration. No resource is created, and there is no `--apply`
option. Resolution does not establish capacity, quota, full network access or
eventual provisioning success. See [CLI planning](docs/cli-planning.md) for
defaults, filters, schema and prepared live verification. Live validation of
this CLI extension remains pending.

Modern `list_all()` calls now fail on detected repeated resource IDs across
pages or unexpected pagination offsets. Traversal is not a snapshot, and
concurrent changes can require a retry. No duplicate or partial result is
returned after those errors.

## Block-storage discovery and selection

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    volume = cloud.volumes.get_by_name("app-data", zone_id=4)
    print(volume.id, volume.attachment_state, volume.is_available)
    unattached = cloud.volumes.list_unattached(zone_id=4)
```

Name lookup and attached/unattached selection follow all collection pages.
Duplicate exact names raise `AmbiguousLookupError`; ordinary `list()` still
returns one page. Attachment state is `attached` when an instance ID is
reported, `unattached` for an explicit null `instanceId`, and `unknown` when
that field is omitted. Unknown volumes are excluded from `list_unattached()`.

`is_available` is a hint requiring explicit unattached evidence and an
`available`, `provisioned`, or `ready` status. Missing status returns False.
It does not reserve the volume or establish provider-side attachability.
`is_attached == False` alone is insufficient to select a volume. When storing
models for later reconstruction, use `model_dump(exclude_unset=True)` to
preserve the difference between omitted fields and explicit null values.
Volume mutation operations and live verification remain pending.

## Backup discovery and recovery preparation

Use `cloud.backups.list_results_page(backup_id)` and `list_jobs_page()` for
typed pagination metadata, or `list_all_results(backup_id)` and
`list_all_jobs()` to traverse the collections. Existing `list_results()` and
`list_jobs()` return one page. Execution methods submit work and reject
explicit failed responses; acceptance does not prove completion or recovery.
See the [backup guide](docs/backup-recovery.md) for examples and verification
limits. Live execution, restore workflows and retention management remain
pending.

## Object-storage configuration

`cloud.storage_buckets` manages MTN Cloud's storage-provider configurations.
Its lookup searches all pages and requires an exact, unique name:

```python
from mtn_cloud import MtnCloudClient

with MtnCloudClient() as cloud:
    bucket = cloud.storage_buckets.get_by_name("backups")
    print(bucket.id, bucket.name, bucket.provider_type)
    # Explicit configuration removal; provider resource removal defaults off:
    # cloud.storage_buckets.delete(bucket.id)
```

Name misses raise `LookupNotFoundError`; duplicate names raise
`AmbiguousLookupError`. Deletion treats HTTP 404 as already absent and reports
an explicit JSON `success: false` as failure. `remove_resources=True` requests
provider resource removal and must be chosen explicitly; a successful request
does not prove backend cleanup or S3 object deletion has completed.

Provider `config` is omitted from model `repr`/`str` output, and rendered model
validation errors hide input values. Configuration remains present in
`model_dump()`, request payloads and structured validation error details.
Avoid logging those values. Malformed or explicitly
rejected get/create/update responses produce `MtnCloudError` with generic
messages and operation context.

See [the configuration example](examples/storage_bucket_config.py). S3 object
transfers, access-key management, and full live lifecycle verification remain
pending; this service manages control-plane configuration only.

## GitHub Action

Use `.github/actions/mtncloud` for read-only inventory and instance planning
from GitHub Actions. The manual **MTN Cloud read-only** workflow uses the
`live-read-only` environment and the existing `MTN_CLOUD_LIVE_TESTS` opt-in
variable. It writes projected JSON results and a job summary. See the
[action guide](docs/github-action.md) for secrets, inputs, exit codes and
artifact handling. Hosted workflow and live MTN verification remain pending.

## Control-plane availability monitor

Run the standalone monitor from an external host to observe console HTTP
availability without SDK credentials:

```bash
uv run python tools/monitor_control_plane.py
uv run python tools/monitor_control_plane.py --watch --interval 60 --failure-threshold 3
```

It emits timestamped JSON with HTTP status, latency, consecutive failures,
and alert/recovery events. Redirects count as unsuccessful. See the
[deployment and signal guide](docs/control-plane-monitor.md) for exit codes,
configuration, and limitations.

## Error handling

Modern client operations raise exceptions from `mtn_cloud.modern_exceptions`:

```python
from mtn_cloud import MtnCloudClient
from mtn_cloud.modern_exceptions import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    MtnCloudError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    TransportError,
)

try:
    with MtnCloudClient() as cloud:
        cloud.instances.get(4737)
except AuthenticationError:
    print("The credential is missing or invalid")
except ForbiddenError:
    print("The credential is not permitted to perform this operation")
except NotFoundError:
    print("The resource does not exist or is not visible to this tenant")
except ConflictError:
    print("The request conflicts with the resource's current state")
except RateLimitError:
    print("The API asked the caller to slow down")
except (TimeoutError, TransportError):
    print("The request did not complete")
except ServerError:
    print("MTN Cloud returned a server-side failure")
except MtnCloudError as exc:
    print(f"MTN Cloud request failed: {exc}")
```

Name-based helpers such as `networks.get_subnet_by_name`,
`networks.get_pool_ip`, `volumes.get_by_name`, `storage_buckets.get_by_name`, `routers.get_interface`, and
layout-name resolution during `instances.provision` raise
`LookupNotFoundError` when nothing matches. It subclasses `NotFoundError` and
is also a `ValueError`, so code written against earlier releases keeps
working. Ambiguous matches raise `ValueError` or its specialized subclass
`AmbiguousLookupError`.

Because Python uses the first matching `except` clause, a lookup miss now
reaches an `except NotFoundError:` or `except MtnCloudError:` clause listed
before an `except ValueError:` clause.

Errors raised for HTTP failures and transport failures also record the
operation that failed:

- `exc.method`
- `exc.path`, without the query string
- `exc.attempts`, counting retries
- `exc.status_code`
- `exc.request_id`

Printing or logging the error shows the method, the path and the request ID.
It shows the attempt count only when the request was retried:

```text
missing (HTTP 404) [GET /instances/5, request_id=req-1]
busy (HTTP 503) [GET /whoami, attempts=3]
```

Connection-failure messages name only the exception type, such as
`ConnectionError`. The original exception, which can include the full URL,
stays available as `exc.__cause__`. Errors raised after a response arrives,
such as `LookupNotFoundError` or invalid-response errors, have these fields
set to `None`.

The package also contains the original legacy client and exception hierarchy
for compatibility. New integrations should use `MtnCloudClient`,
`ClientSettings`, the typed services, and `mtn_cloud.modern_exceptions`.

The top-level `mtn_cloud` namespace exports both hierarchies, and their names
are easy to confuse:

| Top-level name | Hierarchy | Raised by |
| --- | --- | --- |
| `MtnCloudError`, `TransportError`, `ModernTimeoutError` | Modern | `MtnCloudClient` |
| `MTNCloudError` and all other exception names | Legacy | `MTNCloud` |

`ModernTimeoutError` is `mtn_cloud.modern_exceptions.TimeoutError`, renamed at
the top level so it does not shadow Python's built-in `TimeoutError`. To avoid
confusion, import modern exceptions from `mtn_cloud.modern_exceptions`.

## Testing and development

Run the unit suite without making cloud mutations:

```bash
uv run --extra dev pytest -q
```

The live contract tests are opt-in. Read-only checks require both credentials
and an explicit flag:

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 \
  uv run --extra dev pytest tests/integration/test_live_contract.py -q -m "not mutation"
```

Mutation tests create and delete an instance and require a second explicit
guard:

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 \
MTN_CLOUD_ALLOW_MUTATIONS=1 \
  uv run --extra dev pytest tests/integration/test_live_contract.py -q -m mutation
```

Read [`docs/live-contract-tests.md`](docs/live-contract-tests.md) before
running mutation tests. They consume tenant resources and may take many
minutes because MTN Cloud provisioning is asynchronous.

Useful checks during development:

```bash
python -m compileall -q src tests
uv build
git diff --check
```

## Release process

Releases are tag-driven and publish the exact distributions produced by CI.
To prepare a release:

1. Update `version` in `pyproject.toml`, `__version__` in
   `src/mtn_cloud/_version.py`, and the version badge at the top of this README.
2. Move the completed entries in `CHANGELOG.md` into a new version section.
3. Run the unit, quality, and build checks locally.
4. Commit the release preparation changes.
5. Create and push an annotated tag matching the package version, for example:

   ```bash
   git tag -a v0.2.0 -m "Release v0.2.0"
   git push origin v0.2.0
   ```

The release workflow verifies that the tag matches `pyproject.toml`, runs the
full quality gate, builds and validates the distributions, creates a GitHub
Release, attaches the artifacts, and publishes them to PyPI using trusted
publishing. Manual workflow dispatch is restricted to TestPyPI validation.

See [`docs/releasing.md`](docs/releasing.md) for the maintainer checklist and
GitHub environment requirements.

The broader platform roadmap—including storage, IAM, databases, networking,
autoscaling, billing, compliance-enablement, and the planned GitHub Action—is
maintained in [`docs/roadmap.md`](docs/roadmap.md).

## Compatibility and scope

This project targets the MTN Cloud Console API at
`https://console.cloud.mtn.ng/api`. The implementation is intentionally built
from verified API behavior and tenant-scoped contracts. Endpoint availability
can differ by client type, tenant, role, zone, and resource pool.

The SDK does not promise that every endpoint documented by MTN Cloud is
implemented yet. Unsupported services should be added only after their
request, response, permission, and lifecycle behavior has been verified.

## Contributing

1. Create a feature branch.
2. Add or update typed models and service tests.
3. Keep live tests opt-in and protect all mutations with explicit guards.
4. Run the unit suite and package build locally.
5. Update `CHANGELOG.md` for user-visible changes.

Please include a reproducible request shape and a redacted response when
reporting an API compatibility issue. Never include API keys, refresh tokens,
or unredacted tenant data.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).
