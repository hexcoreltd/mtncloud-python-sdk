# Networking contract verification

Networking is partially implemented. A method being present in the SDK does
not mean its full lifecycle has passed a live test. New networking mutations
must have verified MTN request/response shapes and a guarded live test before
being described as supported.

## Verification recorded on 2026-11-05

Credentials were loaded through `ClientSettings`; no credential values were
printed. Authenticated reads of `/api/whoami`, `/api/networks`,
`/api/networks/routers`, and `/api/network-router-types` timed out. Additional
requests to the console root and `/api/whoami` returned HTTP 403 with an HTML
content type. These results do not establish whether the token is valid or
whether the response originates from the application or an intermediary.

No resources were created, changed, or deleted during this verification.
No response fixtures were recorded because no usable JSON contract was
received. Live verification remains blocked by connectivity/access.

The operator also observed HTTP 504 from the browser's `/ping` request while
the HPE Morpheus loading page was displayed. Offline implementation and mocked
testing continue; the next live run must re-establish authenticated access.

## Router reliability implemented offline

- A successful creation response's router ID is preserved in
  `error.response["router_id"]` if the following read or waiter fails.
- HTTP exception classes and operation metadata are preserved.
- Waiter options are validated before a creation request is submitted.
- Deletion treats HTTP 404 as already absent, including deletion races;
  other failures propagate. A JSON `success: false` is reported as failure.
- Waiter timeouts and failed states carry the router ID for recovery.
- The example records the ID before waiting and uses it for optional cleanup.

These behaviors have mocked regression coverage. A guarded create/wait/delete
live test is prepared for a dedicated test subnet; it has not yet run against
a healthy MTN service. See [live test instructions](live-contract-tests.md).

## Operation inventory

| Area | Current SDK operations | Next verification needed |
| --- | --- | --- |
| Networks | List/get, name lookup, create/update/delete | Isolated create/read/update/delete lifecycle and backend readiness |
| Subnets | List and parent-scoped lookup | Actual parent references; separate mutation contract if exposed |
| Routers | List/get, create/delete, readiness/deletion waiters | Full lifecycle, interfaces and external gateway reconciliation |
| Router interfaces | Embedded discovery and subnet lookup | Actual interface shape; attach/detach endpoint and payload |
| Routes | No dedicated service | Endpoint, models and mutation behavior |
| IP pools | Pool and address discovery | Pagination, ownership and allocation semantics |
| Floating IPs | Request external-network assignment during instance provisioning | Standalone discovery, allocation, association and release contracts |
| Security groups | Group and rule CRUD | Dedicated live lifecycle and rule enforcement verification |
| Load balancers/VPN | No dedicated modern service | Tenant availability and provider-specific API contracts |

IP-pool address lookup is not proof of floating-IP support. Likewise,
`networkSubnet` in the router creation payload does not prove that the same
field is returned in a router response.

## Repeatable read-only verification

Network creation preflight is also implemented offline:
`networks.validate_create(request)` validates CIDR/gateway/DNS inputs before
discovery, then checks group/zone association, zone availability, creatable
OpenStack network type and scoped pool membership. `create(validate=True)`
performs the same checks before POST. This is opt-in for compatibility and
does not reserve resources or check provider-side address conflicts. It has
mocked regression tests; its live test remains pending service recovery.

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_networking.py -q -x --tb=short
```

The suite first checks authenticated connectivity, then checks collection
envelopes, detail retrieval, subnet parent references, and embedded router
interfaces. Authentication, permission and connection failures fail the run.
An empty collection skips the associated detail check; that skip must not be
reported as a verified contract. The suite performs GET requests only.

Once access works, capture sanitized successful response fixtures, implement
the next verified mutation, and run its guarded lifecycle test with cleanup.
Record the result here and update the roadmap for each completed operation.
