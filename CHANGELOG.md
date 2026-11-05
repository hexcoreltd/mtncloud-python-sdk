# Changelog

All notable changes to this project are documented in this file.

The project follows [Semantic Versioning](https://semver.org/) where
practical. Until `1.0.0`, minor releases may include API improvements that
would normally require a major release in a mature stable SDK.

## [Unreleased]

### Added

- Optional read-only network creation preflight with `networks.validate_create`
  and `create(validate=True)`, checking addressing and placement dependencies.
  Mocked regression coverage is complete; live verification is pending.

- Dedicated opt-in live networking contract checks and an operation inventory
  separating implemented methods from live-verified lifecycle coverage.

- Rewritten runnable examples for the modern SDK, safe provisioning workflows,
  storage configuration, router management, and CLI inventory usage.
- Read-only `mtncloud` CLI (`[cli]` extra) with `instances`, `networks`, `routers`
  `list`/`describe`, `inventory`, and `version`; versioned JSON output and documented
  exit codes.
- `AmbiguousLookupError` (a `ValueError`), raised when `get_by_name` matches several
  resources. Group and zone ambiguity messages now list the matching IDs.
- `get_by_name()` on instances, networks and routers.
- `list_all()` on modern list services, which follows pagination across all pages.
- Typed read-only subnet lookup by ID and unique name within a parent network.
- Typed router interface discovery and subnet-based interface lookup.
- Typed storage-volume lookup by unique name and unattached-volume discovery.
- Typed network-pool IP lookup by exact address.
- Modern `ForbiddenError` (HTTP 403) and `ConflictError` (HTTP 409) exceptions.
- Modern errors raised by the request pipeline record the failed operation's
  `method`, query-free `path`, and `attempts` (including retries), and show
  them in `str(error)`, for example
  `missing (HTTP 404) [GET /instances/5, request_id=req-1]`.
- `TransportError` messages for connection failures now name only the
  exception type instead of embedding the underlying message, which can include
  the full URL and query parameters. The original exception remains available
  as `__cause__`.

- Modern typed router service with router discovery, external gateway options,
  MTN neutron-router creation/deletion, and readiness/deletion waiters.
- Network type, IP pool, and pool-IP discovery methods.
- Parent-network validation for subnet discovery.
- Modern network create, update, and delete operations using typed payloads.
- High-level instance provisioning support for MTN external-network/floating-IP
  assignment through `external_network_id`.
- Modern snapshot operations for listing, creating, reverting, and deleting
  instance snapshots.
- Modern backup operations for configurations, executions, jobs, and results.
- Modern read-only block-storage volume discovery at `/storage/volumes`,
  including instance attachment filtering.
- Storage-volume type discovery at `/storage/volume-types`, including provider
  options and enabled-type filtering.
- Modern S3-compatible storage-bucket configuration CRUD.
- Modern read-only provisioned-application discovery at `/apps`.

### Changed

- Name-based lookups (`networks.get_subnet`, `networks.get_subnet_by_name`,
  `networks.get_pool_ip`, `volumes.get_by_name`, `routers.get_interface`, and
  layout-name resolution in `instances.provision`) now raise
  `LookupNotFoundError`, a `NotFoundError`, when nothing matches. This is
  consistent with other modern services. Because it is also a `ValueError`,
  existing `except ValueError` handlers still catch it. However, an
  `except NotFoundError:` or `except MtnCloudError:` clause listed before them
  now catches the miss first.
- HTTP 403 and 409 responses now raise `ForbiddenError` and `ConflictError`.
  Both subclass `MtnCloudError`, so existing handlers still catch them.
- The default user agent is derived from the package version, and a
  regression test keeps `pyproject.toml`, `_version.py`, and the README badge
  in sync.
- Clarified the modern and legacy exception exports in the package namespace
  and README.
- Hardened the request and service layers for strict static type checking.
- Standardized repository formatting and lint compliance for CI quality gates.

### Fixed

- Router creation and waiters preserve submitted resource IDs for cleanup on
  follow-up failures, retaining HTTP exception types and request metadata.
- Router creation validates waiter options before submitting a resource;
  deletion handles already-absent resources and rejects `success: false`.
- Router example records the resource ID before waiting and recovers it from
  follow-up errors for optional cleanup. Live lifecycle validation is pending.

- Modern exceptions, including `TimeoutError`, can now be pickled, so they
  can be passed between processes (for example through `multiprocessing` or
  `concurrent.futures`).

### Planned

- Expand coverage for additional MTN Cloud resources and lifecycle operations.
- Add more verified pagination and filtering contracts.
- Add refresh-token exchange when the MTN Cloud authentication flow is fully
  confirmed.
- Improve generated API reference documentation and examples.
- Continue compatibility testing across supported Python versions.

## [0.1.0] - 2026-11-04

First modernized release of the MTN Cloud Python SDK.

### Added

- New `MtnCloudClient` synchronous client with context-manager support.
- `ClientSettings` based on Pydantic Settings with environment variables,
  `.env` loading, explicit base URL and API prefix, timeout, retry, TLS,
  user-agent, and secret-safe credential settings.
- Typed transport and core request layer with bearer authentication, retries
  for retryable idempotent responses, and typed request exceptions.
- Typed services for zones, groups/projects, instance types and layouts,
  service plans, resource pools, compute instances, networks and subnets, and
  security groups and firewall rules.
- High-level instance provisioning that resolves a compatible group, zone,
  instance type, layout, resource pool, and provisioning-scoped service plan.
- Network compatibility validation across zone, group, and resource pool before
  instance creation.
- Instance lifecycle actions for start, stop, restart, and suspend.
- Waiters for running, stopped, status, and deleted states.
- Provisioning dry-run support.
- Opt-in live contract tests with separate mutation authorization.
- Documentation for safe live testing and resource cleanup.
- Reproducible `uv` project metadata and package builds beginning at version
  `0.1.0`.
- MIT license and public package documentation.

### Compatibility

- Preserved the original legacy client and resource modules while introducing
  the modern typed client surface.
- Preserved support for the existing API-key environment configuration while
  standardizing new examples on `MTN_CLOUD_TOKEN`.

### Validation

- Unit test suite passes with 497 tests.
- Read-only live contract checks verified against an MTN Cloud tenant.
- End-to-end instance provisioning, readiness polling, and deletion were
  verified with explicit cleanup.
- Source distribution and wheel build successfully.

[Unreleased]: https://github.com/hexcoreltd/mtncloud-python-sdk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hexcoreltd/mtncloud-python-sdk/releases/tag/v0.1.0
