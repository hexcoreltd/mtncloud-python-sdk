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
| `cloud.volumes` | Discover block-storage volumes, attachments, and volume types |
| `cloud.storage_buckets` | Manage S3-compatible storage-provider configurations |
| `cloud.apps` | Discover provisioned applications and catalog deployments |

Some MTN Cloud endpoints are permission-scoped. A valid credential may be
able to access tenant-scoped endpoints while receiving `403 Forbidden` from
broader catalog endpoints. The SDK surfaces these responses as typed errors;
it does not silently broaden permissions or substitute data.

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
mtncloud version
```

- `mtncloud instances|networks|routers list [--group] [--zone] [--name]`
- `mtncloud <resource> describe <id-or-name> [--group] [--zone]`. An argument
  made only of digits is an ID and ignores `--group` and `--zone`. Anything
  else must match one name exactly.
- `mtncloud inventory [--only R1,R2] [--group] [--zone]`
- `mtncloud version`

Global options are `-o/--output json|table`, `--base-url`, `--timeout` and
`--debug`. `-o` may go before the command or after it, and the value after the
command wins. Running `mtncloud` with no arguments prints help and exits 0.

The default format is `table` when stdout is a terminal and `json` when it is
piped. Table cells are rendered literally. Instance and network `config`
fields are excluded from output. Every command writes only its result to
stdout. Diagnostics and errors go to stderr, and a failed command leaves
stdout empty.

JSON documents carry a versioned `schema`: `mtncloud.list/v1`,
`mtncloud.describe/v1`, `mtncloud.inventory/v1`, `mtncloud.version/v1`, and
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
`networks.get_pool_ip`, `volumes.get_by_name`, `routers.get_interface`, and
layout-name resolution during `instances.provision` raise
`LookupNotFoundError` when nothing matches. It subclasses `NotFoundError` and
is also a `ValueError`, so code written against earlier releases keeps
working. Ambiguous matches still raise a plain `ValueError`.

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
