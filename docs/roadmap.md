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
- S3-compatible storage bucket configuration CRUD
- Provisioned-application discovery
- Unit tests and guarded live contract tests
- `uv` project, package builds, release workflow, and trusted publishing setup

### Quality baseline completed

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

Implemented in the current development line:

- Modern network type discovery
- Network IP-pool and pool-IP discovery
- Parent-network validation for subnet discovery
- Modern network create, update, and delete operations
- High-level floating-IP request support through instance external-network
  configuration
- Modern instance snapshot operations
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
  integration (mocked tests pass; live validation pending)

Prepared for the next healthy live environment:

- Guarded router create/readiness/delete lifecycle test with cleanup using the
  submitted ID, including follow-up read failures. This test requires explicitly
  configured test resource IDs and a dedicated unattached subnet.
- Read-only network preflight test with explicitly configured test placement IDs.

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

- Volumes and volume lifecycle
- Instance volume attachment/detachment
- Volume expansion
- Snapshots and restore workflows
- Virtual images and image metadata
- Backup jobs, schedules, retention, and restore
- Cross-zone or off-site recovery capabilities where supported
- Recovery waiters and operation cleanup
- Backup verification helpers and recovery evidence export

This milestone is essential for financial workloads because local primary
storage without tested backup and recovery is not operational resilience.

### Milestone 3 — Object storage

- Tenant object-storage access-key workflow
- Bucket discovery and configuration
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

- Instance and database metrics
- Logs and log destinations
- Health and availability checks
- Alerts and notification targets
- Operation history
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
  `inventory` and `version` done; `plan` and floating IPs are the next CLI items)
- JSON output for automation
- Human-readable tables for operators
- `plan`, `apply`, `wait`, `destroy`, and `inventory` commands
- GitHub Action built on the CLI
- Terraform/OpenTofu provider
- Reusable CI/CD examples
- Ansible or configuration-management integrations where valuable

## 7. GitHub Actions strategy

The project should provide an official action after the CLI has a stable
command and exit-code contract. The action should not duplicate SDK logic.

Proposed action usage:

```yaml
name: Deploy MTN Cloud

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Plan MTN Cloud changes
        uses: hexcoreltd/mtncloud-python-sdk/.github/actions/mtncloud@v1
        with:
          command: plan
          config: infrastructure/mtncloud.yaml
          api-key: ${{ secrets.MTN_CLOUD_API_KEY }}

      - name: Apply MTN Cloud changes
        uses: hexcoreltd/mtncloud-python-sdk/.github/actions/mtncloud@v1
        with:
          command: apply
          config: infrastructure/mtncloud.yaml
          api-key: ${{ secrets.MTN_CLOUD_API_KEY }}
          confirm: "true"
```

Required action properties should include:

- `command`
- `config` or a structured input source
- `api-key` or a supported credential-provider mode
- `base-url`
- `environment`
- `timeout`
- `wait`
- `confirm` for mutations
- `dry-run`

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

The first action should support read-only inventory and dry-run provisioning
before mutation commands. This gives teams a safe adoption path.

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
   ~~Read-only inventory~~ is done. Dry-run output (`plan`) and floating IPs
   are pending.
6. Implement the first GitHub Action for authenticated inventory and dry-run
   provisioning.
7. Add migration-oriented examples and evidence export.
8. Engage MTN Cloud users and maintainers to verify contracts and document
   tenant-specific permissions.

The project should optimize for trustworthy primitives first. A smaller SDK
that is predictable, safe, and auditable is more useful to regulated teams than
a broad SDK that silently guesses at undocumented API behavior.
