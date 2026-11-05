# Live contract tests

The live tests use credentials from `.env` through `ClientSettings`.

Run read-only checks:

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest tests/integration -q -m "not mutation"
```

The create/delete test is separately guarded because it creates billable
resources:

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 \
MTN_CLOUD_ALLOW_MUTATIONS=1 \
uv run pytest tests/integration/test_live_contract.py -q -m mutation
```

The mutation test selects a network whose zone pool matches the selected
resource pool, waits up to 30 minutes for provisioning, and verifies deletion.

The read-only suite also verifies router discovery, router types, network
types, subnet parent relationships, and provisioned-application discovery.

Focused networking checks, including raw collection envelopes and router
interface responses, are in `tests/integration/test_live_networking.py`.
They authenticate first and fail on connection or permission errors. Empty
collections skip the corresponding detail checks. See
[networking contract status](networking-contracts.md) for the latest evidence
and remaining contract gaps.

## Router lifecycle (pending live verification)

The router test uses a dedicated test subnet supplied by the operator and
does not allocate an external gateway. Use an unattached subnet reserved for
this test; it creates a router and removes that router in `finally`, including
when creation succeeds but a follow-up read or waiter fails. The subnet and
its parent network are retained.

Set `MTN_CLOUD_TEST_GROUP_ID`, `MTN_CLOUD_TEST_ZONE_ID`,
`MTN_CLOUD_TEST_POOL_ID`, and `MTN_CLOUD_TEST_ROUTER_SUBNET_ID` to positive IDs
for that test environment, then run:

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 MTN_CLOUD_ALLOW_MUTATIONS=1 \
uv run pytest tests/integration/test_live_networking.py \
  -q -m mutation --tb=short
```

Both live and mutation flags are required. Missing test resource IDs fail
before creation. Passing unit tests does not mark this lifecycle live-verified;
run it when the MTN control plane is available and record the outcome.

## Network creation preflight (pending live verification)

The read-only `test_live_network_create_preflight` additionally accepts
`MTN_CLOUD_TEST_GROUP_ID`, `MTN_CLOUD_TEST_ZONE_ID`, `MTN_CLOUD_TEST_POOL_ID`,
and `MTN_CLOUD_TEST_NETWORK_TYPE_ID`. It checks placement for a sample
documentation-range CIDR using GET requests only, without creating a network.
If any ID is absent, this specific test skips; invalid supplied IDs fail.

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_networking.py -q -k preflight
```

## Block-storage discovery (pending live verification)

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_block_storage.py -q -x --tb=short
```

This suite uses existing volumes only: it checks collection/detail envelopes,
`instanceId` attachment evidence, and volume-type retrieval. No resources are
created or modified. Authentication/permission/transport errors fail the run.
Empty collections skip item checks; a detail response without `instanceId`
skips ownership verification while asserting the SDK classifies it as unknown.
No fixture or lifecycle contract should be marked verified from those skips.

The same suite includes a CLI `inventory --only volumes` check for the JSON
envelope, attachment-state fields and provider-metadata exclusions. This live
CLI check is prepared but has not been run against a healthy control plane.

## Object-storage configurations (pending live verification)

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_object_storage.py -q -x --tb=short
```

These GET-only tests verify storage-bucket collection/detail retrieval and,
when at least two configurations exist, pagination. Provider credentials are
not printed or saved. Empty collections skip detail checks; missing/insufficient
pagination metadata skips the pagination check. Authentication, permission and
transport errors fail the run. The suite does not create/delete configurations
or S3 objects; mutation lifecycle verification remains pending.
