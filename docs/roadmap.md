# MTN Cloud Python SDK Roadmap

Status: living roadmap  
Package: `mtncloud-python-sdk`  
Python import: `mtn_cloud`  
Current version: `0.1.0`

## 1. Purpose

`mtncloud-python-sdk` is an unofficial, open-source Python SDK for the MTN
Cloud platform. Its goal is to give Nigerian engineering teams a reliable,
typed, testable, automation-friendly foundation for operating MTN Cloud from
Python, CI/CD systems, infrastructure tooling, and internal platforms.

The project is intended to help teams move beyond manually operating the MTN
Cloud Console. It will provide stable abstractions for provisioning,
governance, networking, storage, managed databases, security, observability,
and operational automation.

This SDK is not an MTN product, does not represent MTN, and does not provide a
regulatory certification. A financial institution remains responsible for its
architecture, security controls, data classification, third-party risk,
business continuity, legal interpretation, and regulatory submissions.

## 2. Why this project matters

The Central Bank of Nigeria has issued and publicly discussed requirements
around local storage and management of payment transaction data, with a
reported implementation deadline of 1 January 2027. Public reporting also
emphasizes that localization is broader than copying a database: institutions
need to consider the data lifecycle, transaction systems, logs, metadata,
backups, operational controls, security, resilience, and verification.

The project therefore targets a practical engineering gap:

```text
Regulatory requirement
        ↓
Data inventory and classification
        ↓
Target local architecture
        ↓
Repeatable MTN Cloud infrastructure
        ↓
Security, backups, observability, and recovery
        ↓
Evidence and independent verification
```

The SDK is one part of that chain. It should make the infrastructure layer
repeatable and auditable, while leaving compliance decisions and attestations
to each institution and its advisers.

Primary references:

- [CBN IT Standards Blueprint](https://www.cbn.gov.ng/itstandards/IT_Standards_Blueprint%20v2.2_for_DMBs.pdf)
- [MTN Cloud documentation](https://cloud.mtn.ng/documentation)
- [MTN Cloud product and service catalog](https://cloud.mtn.ng/documentation/guide/product-service-catalog)
- [MTN Cloud managed database workflow](https://cloud.mtn.ng/documentation/guide/managed-database-provisioning)
- [MTN Cloud object storage workflow](https://cloud.mtn.ng/documentation/guide/object-storage-provisioning-workflow)
- [MTN Cloud users and roles workflow](https://cloud.mtn.ng/documentation/guide/users-roles-management-workflow)
- [MTN Cloud network and router workflow](https://cloud.mtn.ng/documentation/guide/network-router-creation-workflow)
- [MTN Cloud VM autoscaling workflow](https://cloud.mtn.ng/documentation/guide/vm-auto-scaling-instances)

The exact regulatory scope, covered institutions, effective requirements, and
interpretation of any CBN circular must be confirmed from the applicable
official circular and qualified legal/compliance advisers. This roadmap must
not be used as legal advice.

## 3. Product principles

### Contract before convenience

Every service begins with verified request and response contracts. Console
behavior, endpoint permissions, tenant-specific fields, and asynchronous state
transitions must be recorded before a high-level abstraction is declared
stable.

### Safe by default

- Mutating operations require explicit calls.
- Provisioning supports dry-run resolution before creation.
- Live tests are opt-in.
- Destructive tests require a separate mutation guard.
- Secrets are never logged or placed in request errors.
- CI uses least-privilege GitHub permissions.

### Typed but not brittle

Responses are represented by typed Pydantic models, while forward-compatible
unknown fields are handled deliberately. API quirks should be isolated in
service adapters instead of leaking into every caller.

### Automation-first

Every important Console operation should eventually be usable from Python,
the CLI, CI/CD, and infrastructure-as-code integrations without requiring
browser interaction.

### Evidence-friendly

Operations should expose request IDs, resource IDs, timestamps, status
transitions, and sanitized operation summaries suitable for change records and
internal audit trails.

### Provider boundaries are explicit

The MTN Cloud control-plane API, S3-compatible object storage, SSH, database
protocols, and external observability destinations are different interfaces.
They should not be hidden behind one ambiguous client abstraction.

## 4. Current implementation: `0.1.0`

### Implemented modern client surface

- `MtnCloudClient` synchronous client with context-manager support
- `ClientSettings` with `.env` and `MTN_CLOUD_*` environment support
- Bearer-token/API-key authentication configuration
- Configurable timeout, retries, TLS verification, and user-agent
- Typed transport and core error mapping, with request ID and operation
  metadata on every pipeline error
- Zones and deployment clouds
- Tenant groups/projects
- Instance types and layouts
- General and provisioning-scoped service plans
- Resource-pool discovery
- Compute instance list/get/create/update/delete operations
- Instance start, stop, restart, and suspend operations
- Status waiters for running, stopped, and deleted instances
- High-level instance provisioning workflow
- Provisioning dry-run resolution
- Network and subnet discovery
- Typed subnet lookup by ID and unique name within a parent network
- Typed network-pool IP lookup by exact address
- Security groups and firewall rules
- Network compatibility validation against zone, group, and resource pool
- Router and external-network discovery plus lifecycle waiters
- Snapshot and backup discovery and lifecycle operations
- Storage volume and volume-type discovery
- Read-only virtual-image discovery and metadata (MTN live verification pending)
- S3-compatible storage bucket configuration CRUD
- Provisioned-application discovery
- Unit tests and guarded live contract tests
- `uv` project, package builds, release workflow, and trusted publishing setup

### Quality baseline completed

- CLI help-scope regressions cover plain and forced-color rendering, with ANSI
  normalization before option assertions so terminal styling does not fail CI.

- Strict mypy validation passes across the modern and legacy source tree.
- Ruff formatting and lint checks pass in local and CI environments.
- Unit tests and package builds remain green after the typing and formatting
  hardening work.

### Existing legacy surface

The repository also contains older resource managers and models for parts of:

- Routers
- Volumes
- Backups and snapshots
- Virtual images
- Storage buckets
- Archive buckets
- Legacy instance, network, and security-group operations

These modules are valuable migration references, but they are not automatically
considered part of the modern stable surface until their contracts are
reviewed, typed, tested, and validated against the current API.

## 5. Target architecture

The long-term package should expose clear service namespaces:

```python
with MtnCloudClient() as cloud:
    cloud.compute.instances
    cloud.networking.networks
    cloud.networking.routers
    cloud.storage.volumes
    cloud.storage.snapshots
    cloud.storage.object_storage
    cloud.databases.managed
    cloud.iam.users
    cloud.iam.roles
    cloud.automation.autoscaling
    cloud.observability.metrics
    cloud.billing.invoices
```

The exact public names may evolve, but the design should keep these domains
separate. A compatibility layer can preserve the current flat properties such
as `cloud.instances` and `cloud.networks` while the grouped API matures.

Core layers:

1. **Transport** — HTTP, timeouts, retries, TLS, request IDs, redaction.
2. **Authentication** — static tokens now; refresh and credential providers later.
3. **API core** — status mapping, pagination, envelopes, validation, tracing hooks.
4. **Domain services** — compute, networking, storage, IAM, databases, and so on.
5. **Operations** — waiters, asynchronous jobs, idempotency, polling, cleanup.
6. **CLI** — discover, plan, apply, wait, export, and audit commands.
7. **GitHub Action** — safe CI/CD entry point built on the CLI.
8. **IaC integrations** — Terraform/OpenTofu provider and reusable modules later.

## 6. Roadmap by milestone

### Milestone 0 — Foundation and contract discipline

Status: **in progress / foundation released**

- Stabilize package identity as `mtncloud-python-sdk`.
- Maintain Python 3.10+ support.
- Keep unit tests deterministic and live tests explicitly guarded.
- Add a sanitized contract-fixture format for each service.
- Add standard request ID and operation metadata to exceptions. **Done:**
  modern errors carry `request_id`, `method`, `path`, and `attempts`.
- Define deprecation and compatibility policy for legacy modules.
- Add release notes and migration guidance for every public API change.

### Milestone 1 — Networking foundation

Priority: **current implementation milestone**

Progress: **partially implemented**

Live verification update (2026-11-05): authenticated networking probes timed
out; additional console and `/api/whoami` probes returned HTML HTTP 403.
New mutation contracts remain unverified. A dedicated read-only networking
suite now checks envelopes, detail retrieval, subnet parent references and
embedded router interfaces. See [networking contract status](networking-contracts.md)
for the operation inventory and access blocker. IP-pool discovery must not be
counted as standalone floating-IP lifecycle support.

Later on 2026-11-05 the control plane recovered, and the read-only live suite
ran against a real tenant: 17 tests passed, and 16 were skipped for lack of
resources such as backups, snapshots and bucket configurations. The read-only
networking checks, instance snapshot listing and process detail now pass live.
The run found three contract mismatches, all now fixed with regression tests:
integer `datastoreId` on volumes, integer `subId` on processes, and an
over-reported virtual-image `meta.total`. MTN Cloud returns no request-ID
header, so `request_id` is empty on errors from this provider.

Implemented in the current development line:

- Modern network type discovery
- Network IP-pool and pool-IP discovery
- Parent-network validation for subnet discovery
- Modern network create, update, and delete operations
- High-level floating-IP request support through instance external-network
  configuration
- Modern instance snapshot operations (upstream contract correction implemented;
  MTN live verification remains pending)
- Modern backup configuration, job, execution, and result operations
- Modern read-only block-storage volume discovery and attachment filtering
- Storage-volume type and provider-option discovery
- Typed storage-volume lookup by unique name and unattached-volume discovery
- Modern S3-compatible storage-bucket configuration CRUD
- Modern router listing and retrieval
- External gateway discovery
- MTN neutron-router creation and deletion
- Router readiness and deletion waiters
- Typed router interface discovery and subnet-based interface lookup
- Router lifecycle recovery IDs, preflight waiter validation and idempotent
  deletion (implemented with mocked regression coverage; live verification pending)
- Read-only network creation preflight covering addressing and group, zone,
  type and resource-pool dependencies; optional `create(validate=True)`
  integration (verified live 2026-11-05)

Verified live with guarded mutation tests (2026-11-05):

- Network create (with preflight) and delete, using a throwaway network.
- Router create, readiness and delete, attached to that throwaway network's
  subnet so no existing subnet is touched.
- Instance provisioning from explicit selectors: dry run, create, wait until
  running and force delete (one small instance, about 3 minutes).
- Network create preflight with tenant credentials, which cannot read
  `/zones/{id}`; that lookup's 403 now skips only the zone-enabled check.

Provider behaviour found by these runs:

- Just after a network is created, its subnet listing returns another
  network's subnet for about 10 seconds. `list_subnets` drops it.
- Router interfaces reference the network and CIDR, not the subnet.
  `routers.get_interface(router_id, subnet_id)` now falls back to the subnet's
  parent network and CIDR, skipping gateway networks the tenant cannot read
  (verified live against two existing routers).

Still to implement and verify:

- Subnets CRUD and IP allocation behavior (the current documentation describes
  subnet creation as part of network creation but does not establish a
  standalone mutation contract)
- Standalone volume CRUD and attachment operations, once their API contract is
  verified
- Standalone floating-IP allocation/association endpoints, if exposed by the
  current MTN Cloud API contract
- Router interface attach/detach and route management (mutation contract pending)
- Floating/public IP allocation and association
- Broader network topology/dependency graph and provider-side address-conflict checks
- Load balancers where the API contract is available
- VPN and private connectivity discovery where enabled for the tenant

Why first: networking is a dependency for VMs, managed databases, storage
integrations, security boundaries, and highly available applications.

### Milestone 2 — Block storage, images, backup, and recovery

Progress: **read-only discovery and selection implemented; lifecycle pending**

- Volume name lookup and attached/unattached selection now traverse all pages.
- Attachment evidence distinguishes attached, explicitly unattached and unknown;
  missing fields no longer imply availability. Availability remains a local hint.
- Mocked regressions cover pagination, duplicate names, partial metadata and
  failures on later pages. A read-only block-storage live suite is prepared;
  verification is deferred until service recovery.
- Backup result/job page and all-page methods reuse the common collection
  adapter, with parent-result validation and local pagination checks.
- Execution submissions and configuration deletion reject explicit failed
  responses. Accepted submissions are not interpreted as completed backups.
- Mocked backup regressions pass and read-only configuration/result/job live
  checks are prepared. Offset support and lifecycle behavior remain pending
  live verification; see [backup guide](backup-recovery.md).
- Modern virtual-image list/page/all-page/get/exact-name lookup is implemented,
  using the existing endpoint and upstream image-origin filters. Models accept
  named metadata tags alongside legacy strings and retain unknown visibility
  and origin as unknown. Mocked regressions, an example and guarded read-only
  live checks are prepared; MTN verification remains pending. See the
  [virtual-image guide](virtual-images.md).
- Shared pagination treats `meta.size` as page-local when `meta.total` is
  absent, avoiding truncated discovery across modern collection services.
- Snapshot adapters now follow upstream asynchronous creation and global
  detail/deletion contracts. Submission process IDs replace the previous
  assumed snapshot return. Scoped lookup and restore/deletion membership checks,
  explicit acknowledgements and compatible metadata models have mocked
  regression coverage. Live (2026-11-05): instance snapshot listing passes,
  and the creation endpoint answers, but MTN refuses snapshots for the
  `MTN-U24.04LTS` instance type and exposes no capability flag. The guarded
  lifecycle test is ready for a snapshot-capable type; restore, deletion and
  completion policies remain unverified. See [snapshot guide](snapshots.md).
- Process detail/history and caller-configured status polling now support
  inspecting snapshot submission IDs, with instance/event parent checks and
  no implicit status mapping. Mocked regressions and GET-only live checks are
  prepared; MTN semantics, permissions and recovery validation remain pending.
  See [process guide](processes.md).

Still to implement and verify:

- Volumes and volume lifecycle
- Instance volume attachment/detachment
- Volume expansion
- Live snapshot/process validation, verified completion policies and tested restore workflows
- Live verification of image discovery, metadata and origin-filter semantics
- Image import/upload, deletion and provisioning compatibility
- Backup jobs, schedules, retention, and restore
- Cross-zone or off-site recovery capabilities where supported
- Recovery waiters and operation cleanup
- Backup verification helpers and recovery evidence export

This milestone is essential for financial workloads because local primary
storage without tested backup and recovery is not operational resilience.

### Milestone 3 — Object storage

Progress: **control-plane configuration CRUD implemented; data plane pending**

Implemented offline reliability improvements:

- Bucket name lookup traverses all pages and reports typed missing/ambiguous
  lookups, without returning partial results after a later-page failure.
- Detail and mutation adapters reject explicit `success: false` envelopes;
  malformed detail responses raise SDK errors with generic messages.
- Configuration deletion handles already-absent records and keeps provider
  removal explicitly opt-in. Backend/object cleanup is not inferred from HTTP
  success.
- Provider configuration is hidden from model `repr`/`str` and rendered model
  validation errors hide inputs. Serialization retains configuration; raw
  dumps and structured validation error details remain sensitive.
- Mocked regression coverage is complete; read-only collection/detail/pagination
  live tests are prepared. Full live lifecycle validation remains pending.

Still to implement and verify:

- Tenant object-storage access-key workflow
- Live lifecycle validation of bucket configurations
- S3-compatible endpoint configuration
- A separate S3 client adapter using the generated access credentials
- Bucket policy and access mode support where exposed
- Versioning, retention, lifecycle, and backup-target configuration
- Multipart upload/download helpers
- Credential rotation and secret redaction

Object storage should be treated as two layers: MTN Cloud control-plane bucket
management and S3-compatible data-plane object operations.

### Milestone 4 — IAM, governance, and audit

Status: **contract discovery pending**

The current tenant credential verifies `/whoami`, but candidate collection
paths for users, roles, permissions, and API keys have not produced a stable
typed contract. No IAM mutation endpoint will be guessed or added until MTN
Cloud documentation or a verified tenant response establishes the request,
response, and permission model.

- Users and invitations
- Roles and role assignments
- Permission and policy discovery
- Tenant/group membership
- API client credentials and credential rotation
- Session and access controls
- Activity/audit events
- Least-privilege policy helpers
- Exportable governance inventory

IAM is a security-sensitive area. Predefined provider roles must not be
silently deleted or modified by convenience methods. All IAM mutations should
require explicit confirmation and provide a dry-run representation.

### Milestone 5 — Managed databases

Progress: **application discovery implemented; managed-database workflow pending**

- Provisioned application discovery at `/apps`
- Exact-name application lookup across all pages with optional group scope.
- Read-only application CLI list/describe and opt-in inventory, with filtered
  operational output and sanitized normal errors. Live verification remains
  pending. This does not complete managed-database provisioning or management.
- Shared pagination returns each resource ID once, rejects offset mismatches
  and handles reported page-size caps; it tolerates MTN's over-reported
  `meta.total` (verified live 2026-11-05). GET-only application live
  checks are prepared, including an optional configured-name lookup.

- Managed database application discovery
- Catalog-based provisioning requests
- MySQL, PostgreSQL, MariaDB, and MongoDB workflows where enabled
- Database engine/version validation
- Database users and access levels
- Database configuration and parameter management
- SSL and allowed-CIDR configuration
- Connection-details retrieval with secret-safe models
- Monitoring and logging destinations
- Database operation waiters and rollback/cleanup guidance

Managed databases should not be implemented as ordinary VM wrappers. The API
documentation describes application/catalog workflows, associated instances,
database-specific management tabs, and asynchronous deployment states.

### Milestone 6 — Automation and autoscaling

- Scale thresholds
- VM scale sets and node-group abstractions where supported
- Autoscaling policies
- CPU, memory, and disk threshold rules
- Scheduled actions
- Policy validation and conflict detection
- Preview of scale-out/scale-in effects
- Safe policy deletion and rollback
- Automation activity history

Autoscaling needs strong safeguards because a valid policy can create cost and
availability consequences without a direct user request at runtime.

### Milestone 7 — Observability and operations

Implemented: standalone external HTTP control-plane monitor under `tools/`,
with unauthenticated `/ping` checks, JSON records, latency, failure thresholds
and recovery events. This measures HTTP availability only; authenticated
readiness, notification delivery and wider observability remain pending.
See [monitor deployment guide](control-plane-monitor.md). Mocked regression
coverage is complete; the healthy MTN `/ping` body contract remains unverified.

Read-only process history/detail and explicit status polling are implemented
with typed event records, identity checks and representation-safe log fields.
History returns the provider-selected page only; paging query contracts and
MTN status semantics remain unverified. Mocked regressions pass and guarded
live reads are prepared. See [process guide](processes.md).

- Instance and database metrics
- Logs and log destinations
- Health and availability checks
- Alerts and notification targets
- Operation history export and wider event integrations
- Polling and event hooks
- Resource inventory export
- Change and audit evidence export
- OpenTelemetry integration hooks

### Milestone 8 — Billing and cost management

- Invoices
- Usage reports
- Cost and resource summaries
- Budgets and thresholds
- Project/group chargeback reports
- Export to CSV/JSON
- Currency and billing-period modeling
- Cost estimation for dry-run provisioning plans

Billing data should be read-only by default and separated from resource
mutation services.

### Milestone 9 — Marketplace, applications, and web hosting

- Catalog discovery
- Application order/provisioning
- Application status and associated resources
- Marketplace template parameters
- Web-hosting workflows
- WordPress and common application templates where supported
- Application logs, credentials, and lifecycle operations

### Milestone 10 — CLI, GitHub Action, and infrastructure integrations

- Official `mtncloud` command-line interface (read-only `list`, `describe`,
  `inventory`, `version` and dry-run `plan` implemented; floating IPs pending)
- Read-only instance planning emits `mtncloud.plan/v1` JSON or tables using the
  existing SDK resolver, with selected placement IDs, requested options and
  sanitized errors. Dependency lookups traverse group/zone/type pages and fail
  on typed ambiguity, including duplicate named layouts. Mocked regression
  coverage passes; a configured GET-only live check is prepared and MTN live
  verification remains pending. See [CLI planning](cli-planning.md).
- Volume list/describe and opt-in volume inventory, with zone-only scope,
  attachment evidence and scalar-field output. Existing default inventory
  remains unchanged. Mocked CLI regression coverage is complete; live verification
  is deferred until control-plane recovery.
- Storage-bucket configuration list/describe and opt-in inventory, using an
  explicit scalar-field projection and sanitized normal error messages.
  Unsupported group/zone scope fails before requests. Mocked regression
  coverage is complete and a read-only live CLI check is prepared; live
  verification is deferred. No object data-plane or CLI mutation support is implied.
- Backup configuration list/describe and opt-in inventory, job listing and
  execution-history commands. Output excludes nested provider metadata and raw
  result errors. Mocked regression coverage is complete and guarded read-only
  live CLI checks are prepared; live verification remains deferred.
- JSON output for automation
- Human-readable tables for operators
- `plan`, `apply`, `wait`, `destroy`, and `inventory` commands
- GitHub Action built on the CLI: read-only inventory/plan implemented with
  structured inputs, GET-only transport enforcement, projected JSON artifacts
  and job summaries. A manual workflow is prepared; mocked adapter coverage
  passes. Hosted workflow execution and MTN live verification remain pending.
  See [action guide](github-action.md).
- Terraform/OpenTofu provider
- Reusable CI/CD examples
- Ansible or configuration-management integrations where valuable

## 7. GitHub Actions strategy

The first action is implemented for inventory and dry-run planning through
the CLI. It has structured inputs, isolated locked CLI dependencies, pinned
setup actions, credential masking, a GET-only transport guard, projected JSON
results and sanitized job summaries. Hosted and live validation remain pending.
The manual `.github/workflows/mtncloud-read-only.yml` workflow uses protected
environment secrets and the `MTN_CLOUD_LIVE_TESTS` opt-in variable. See the
[action guide](github-action.md) for current inputs and result contracts.

Local action usage after checking out this repository:

```yaml
name: MTN Cloud discovery

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  inventory:
    runs-on: ubuntu-latest
    environment: live-read-only
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4

      - name: Discover MTN Cloud resources
        uses: ./.github/actions/mtncloud
        with:
          command: inventory
          only: instances,networks,routers
          token: ${{ secrets.MTN_CLOUD_TOKEN }}
```

Future extensions, after their SDK and live contracts are established:

- `config` or a structured input source
- Additional credential-provider modes
- `wait`
- `confirm` for mutations
- Apply/destroy commands and explicit mutation previews
- Offline/bootstrap support for restricted self-hosted runners

Security requirements:

- Never print credentials or authorization headers.
- Mask all secret inputs immediately.
- Use environment-scoped GitHub secrets.
- Default to read-only discovery or plan behavior.
- Require explicit confirmation for apply/destroy operations.
- Produce sanitized operation summaries in `GITHUB_STEP_SUMMARY`.
- Fail closed when required inputs are missing.
- Avoid accepting secrets through command-line arguments where possible.
- Pin action dependencies and document release tags.
- Support self-hosted runners without assuming public network access.

Mutation commands remain pending and are not accepted by the current action.

## 8. Compliance-enablement features

The SDK should help teams produce engineering evidence, without claiming that
the evidence itself proves regulatory compliance.

Planned evidence capabilities:

- Resource inventory export with location and ownership
- Data-plane endpoint and region metadata
- Backup policy and last-successful-backup evidence
- Recovery-test records
- IAM role and permission inventory
- Security-group and network exposure summaries
- Audit/event export
- Configuration snapshots
- Operation request IDs and timestamps
- Sanitized release/deployment manifests
- Drift detection between declared and observed infrastructure

Recommended companion materials for financial institutions:

- Data classification and residency checklist
- Migration runbook
- Business continuity and disaster-recovery runbook
- Vendor and third-party risk checklist
- Access review procedure
- Incident response procedure
- Retention and secure-disposal procedure
- Independent validation and sign-off checklist

## 9. Release and compatibility policy

- `0.x` releases may evolve public APIs while the modern surface is built.
- Stable services require unit tests, fixtures, documentation, and live
  contract validation where safe.
- Destructive changes require changelog entries and migration notes.
- Legacy APIs remain supported until a deprecation path is documented.
- Release artifacts are built once and reused for GitHub Releases and PyPI.
- Live mutation tests never run as ordinary pull-request CI.
- Endpoint availability is always tenant, role, client-type, and region aware.

## 10. Definition of done for a service

A service is ready for a public modern SDK release when it has:

- Typed response and request models
- Documented service methods and examples
- Correct pagination and filtering behavior
- Typed error behavior
- Request/response fixtures
- Unit coverage for success and failure cases
- Permission and client-type notes
- Idempotency and retry analysis
- Waiters for asynchronous operations where required
- Dry-run or preview behavior for risky mutations
- Safe cleanup path
- Read-only live contract test
- Mutation live test, when safe and explicitly guarded
- Changelog entry

## 11. Immediate next actions

1. Publish this roadmap and collect feedback from Nigerian engineering teams.
2. Create a service-contract inventory for networking, storage, IAM,
   databases, automation, operations, and billing.
3. Promote routers, subnets, floating IPs, and volumes from legacy code into
   modern typed services.
4. ~~Add operation metadata and request-ID propagation to the core client.~~
   Done.
5. Build the `mtncloud` CLI around read-only inventory and dry-run output.
   ~~Read-only inventory and dry-run output (`plan`)~~ are implemented.
   CLI plan live verification and standalone floating IPs remain pending.
6. Implement the first GitHub Action for authenticated inventory and dry-run
   provisioning. Implemented; hosted workflow and live MTN validation pending.
7. Add migration-oriented examples and evidence export.
8. Engage MTN Cloud users and maintainers to verify contracts and document
   tenant-specific permissions.

The project should optimize for trustworthy primitives first. A smaller SDK
that is predictable, safe, and auditable is more useful to regulated teams than
a broad SDK that silently guesses at undocumented API behavior.
