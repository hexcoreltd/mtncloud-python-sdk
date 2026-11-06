# Changelog

All notable changes to this project are documented in this file.

The project follows [Semantic Versioning](https://semver.org/) where
practical. Until `1.0.0`, minor releases may include API improvements that
would normally require a major release in a mature stable SDK.

## [Unreleased]

### Added

- Read-only `cloud.processes` history/detail discovery, typed process/event
  models, identity and parent checks, and caller-configured status polling.
  History retains provider page metadata without undocumented paging controls;
  status matching does not infer snapshot readiness. Added a safe example and
  guarded GET-only live checks. MTN validation remains pending.

- Typed asynchronous `SnapshotSubmission`, global snapshot detail/deletion
  service, instance-scoped ID/name lookup, upstream metadata fields and guarded
  GET-only contract checks. Added a read-only example and migration guide.
  MTN live verification and recovery completion tracking remain pending.

- Composite GitHub Action for read-only inventory and dry-run planning, with
  locked CLI dependencies, SHA-pinned setup actions, credential masking,
  a GET-only transport guard, projected JSON results and job summaries.
  Added an opt-in manual workflow and mocked adapter coverage. Hosted workflow
  execution and live MTN verification remain pending.

- Read-only `mtncloud plan` with versioned JSON/table output, placement
  resolution through the existing SDK dry run, input validation, sanitized
  errors and a guarded live check. No creation or apply path is exposed.
  Mocked regressions pass; CLI live verification remains pending.

- Modern read-only virtual-image service with typed metadata, pagination,
  exact-name lookup, image-origin filters and pre-request input validation.
  Image tags accept upstream name/value objects alongside legacy strings;
  rendered validation errors hide inputs. Added an example and guarded GET-only
  contract checks. MTN-specific live verification remains pending.

- Exact-name application SDK lookup and read-only `apps` CLI list/describe and
  opt-in inventory, with group scope and filtered output. Prepared GET-only
  application contract tests; live validation remains pending.

- Read-only backup CLI configuration list/describe, job listing, execution
  history and opt-in inventory, with filtered output and sanitized normal
  errors. Added SDK exact-name backup lookup. Mocked regression coverage is
  complete; live verification remains pending.

- Typed backup result/job pages and all-page collection methods, parent-result
  validation and opt-in read-only live backup contract tests. Live verification
  remains pending.

- Read-only CLI storage-bucket configuration list/describe and opt-in inventory,
  with scalar-only output, sanitized normal errors and pre-request rejection
  of unsupported group/zone scopes. Default inventory remains unchanged;
  live validation is pending.

- Opt-in read-only object-storage configuration contract tests, sharing the
  authenticated storage fixture. Live verification remains pending.

- Read-only CLI volume list/describe and opt-in volume inventory, with zone
  scope, attachment-state output and provider-metadata exclusions. Default
  inventory sections remain unchanged. Live validation is pending.

- Explicit volume `attachment_state` and `is_unattached` helpers, plus opt-in
  read-only live block-storage contract tests (live verification pending).

- Standalone external control-plane HTTP monitor with JSON records, timeout
  handling, unauthenticated probes, and failure/recovery events in watch mode.

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

- **Breaking:** modern `instances.create_snapshot` uses the documented
  asynchronous PUT and returns process IDs in `SnapshotSubmission`, replacing
  the previous POST/`Snapshot` assumption. Snapshot deletion uses `/snapshots/{id}`;
  scoped restore/deletion checks instance collection membership first. Writes
  require explicit acknowledgement and remain single-attempt. Legacy resource
  managers retain their existing API; see `docs/snapshots.md` for migration.

- Provisioning dependency group/zone name and instance-type name/code lookups
  traverse all pages. Duplicate named layouts and ambiguous type/plan/pool/zone
  selections raise `AmbiguousLookupError` (still a `ValueError`). Pool and
  provisioning-plan discovery reject malformed or explicitly failed envelopes.

- Shared collection pagination no longer treats page-local `meta.size` as the
  collection total when `meta.total` is absent, avoiding premature truncation.

- Shared `list_all()` rejects unexpected nonempty-page offsets, respects
  reported page-size caps and rejects non-integer page sizes. It returns each
  resource ID once: repeated IDs are dropped, pages are followed until the
  offset reaches `meta.total`, and without a total a page with no new IDs ends
  pagination (see Fixed).
- Application model representations omit config and rendered validation errors
  hide inputs. Raw serialization and structured errors remain sensitive.

- Backup pagination rejects invalid limits and offsets before requests.
- Shared page adapters use requested offset/limit as metadata fallbacks and
  preserve explicit zero totals.

- Storage-bucket name lookup traverses all pages and uses `LookupNotFoundError`
  and `AmbiguousLookupError`. Both remain compatible with their existing base
  exception types (`NotFoundError` and `ValueError`, respectively).
- Provider configuration is hidden from storage-bucket model `repr`/`str`
  output and rendered model validation errors hide input values. Configuration
  remains available in serialization and API payloads.

- Volume name lookup and attached/unattached selection now traverse all pages;
  duplicate volume names raise `AmbiguousLookupError` (also a `ValueError`).
- `list_unattached()` excludes volumes with omitted `instanceId` metadata.
  `is_available` requires explicit unattached evidence and a recognized status;
  missing attachment or status metadata no longer implies availability.

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

- CLI help-scope tests normalize ANSI styling before checking option names,
  fixing the CI failures with colored help output. Volume and application help
  regressions exercise both plain and forced-color rendering.

- Live MTN contract mismatches found on 2026-11-05:
  - `routers.get_interface(router_id, subnet_id)` finds MTN interfaces, which
    carry a network reference and CIDR but no subnet reference, by checking each
    interface's network for the subnet and matching its parent and CIDR.
    Networks returning 404, such as gateway networks, are skipped; a 403 is
    raised when nothing matched. Ambiguity now
    raises `AmbiguousLookupError` (still a `ValueError`).
  - `networks.list_subnets` drops subnets whose parent reference names another
    network instead of raising. Just after a network is created, MTN returns
    another network's subnet for its subnet listing until the new subnet
    exists; callers now see an empty list and can poll.
  - `networks.validate_create` no longer fails for tenant credentials, which
    get HTTP 403 on `/zones/{id}`. A 403 on that lookup now skips only the
    zone-enabled check; group membership, network type and resource pool are
    still verified, and every other 403 still raises.
  - `StorageVolume.datastore_id` accepts the integer `datastoreId` MTN returns,
    which previously broke volume listing and the `mtncloud volumes` commands.
  - `Process.sub_id` accepts the integer `subId` MTN returns for some
    processes, which previously broke process history.
  - `list_all()` no longer raises "repeated resource IDs" when MTN reports a
    `meta.total` larger than the unique items it returns, which previously broke
    `virtual_images.list_all()` and image name lookup.

- Backup execution submissions and deletion reject explicit `success: false`
  responses; shared collection/detail adapters also reject failed envelopes
  even when otherwise valid resource data is present.

- Storage-bucket detail/mutation adapters reject explicit `success: false`
  responses and wrap malformed detail payloads in SDK errors with generic
  messages. Deletion treats HTTP 404 as already absent and keeps backend
  resource removal opt-in. Live lifecycle verification is pending.

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
