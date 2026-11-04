# Changelog

All notable changes to this project are documented in this file.

The project follows [Semantic Versioning](https://semver.org/) where
practical. Until `1.0.0`, minor releases may include API improvements that
would normally require a major release in a mature stable SDK.

## [Unreleased]

### Added

- Modern typed router service with router discovery, external gateway options,
  MTN neutron-router creation/deletion, and readiness/deletion waiters.
- Network type, IP pool, and pool-IP discovery methods.
- Parent-network validation for subnet discovery.
- Modern network create, update, and delete operations using typed payloads.

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
