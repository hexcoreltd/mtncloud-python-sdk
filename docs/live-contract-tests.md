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
