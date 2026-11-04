# Live contract tests

The live tests use credentials from `.env` through `ClientSettings`.

Run read-only checks:

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest tests/integration/test_live_contract.py -q
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
