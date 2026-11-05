# Instance planning from the command line

`mtncloud plan` resolves instance placement through the SDK's existing
`instances.provision(dry_run=True, wait=False)` workflow. Discovery uses GET
requests only. It does not create an instance, wait for provisioning or accept
an apply flag. MTN live verification of this CLI extension remains pending.

## Usage

Install `mtncloud-python-sdk[cli]` and configure `MTN_CLOUD_TOKEN` or the
compatible `MTN_CLOUD_API_KEY` through your environment or local `.env`.

```bash
mtncloud plan --name api-01 --type-code MTN-CS10 \
  --group production --plan G1S1 -o json > plan.json

mtncloud plan --name api-01 --type-code MTN-CS10 \
  --group 621 --zone 4 --layout 327 --resource-pool 214 \
  --plan 6923 --network-id 298 --root-volume-size-gb 10 -o table
```

Replace sample selections with your tenant's values. Names, codes and IDs
follow the existing SDK resolver: group/zone accept names or IDs; plan accepts
name, code or ID; pool accepts name, code or ID; layout accepts name or ID.
Numeric selectors must be positive. Network ID and root size must also be
positive integers. Empty selectors and names over 255 characters fail before
client creation. Type codes are required and are not image IDs.

Omitted zone and layout use the SDK's first associated zone/default layout.
Omitted resource pool requires one available pool. Omitted network makes no
network selection or compatibility check. The root size defaults to 10 GiB;
`--security-group` defaults to `default`; user creation defaults to true and
can be disabled with `--no-create-user`. Optional `--external-network-id`
records the external network reference intended for later provisioning.
Use explicit selections for reproducible CI runs.

## Output contract

Success exits 0. Nonterminal output defaults to JSON; terminal output defaults
to a table. `-o json|table` works globally or on the command, with the command
option taking precedence. Global `--base-url`, `--timeout` and `--debug`
retain their existing behavior.

```json
{
  "schema": "mtncloud.plan/v1",
  "resource": "instances",
  "dry_run": true,
  "resolved": {
    "name": "api-01",
    "cloud": "MTNNG_CLOUD_AZ_1",
    "group_id": 621,
    "zone_id": 4,
    "type": "MTN-CS10",
    "layout": 327,
    "plan": 6923,
    "resource_pool_id": "pool-214"
  },
  "options": {
    "network_id": 298,
    "external_network_id": null,
    "root_volume_size_gb": 10,
    "security_group": "default",
    "create_user": true
  }
}
```

`resolved` contains selected placement identifiers. `options` records the
requested settings and defaults; null network references mean none was
supplied. These fields form a review summary, not a provider request payload
or an executable saved plan. Unknown resolver fields and raw configuration,
pricing, tags, credentials and provider payloads are excluded. No cost
estimate is calculated. Within schema v1, fields may be added but existing
fields will not be removed or renamed.

Failures leave stdout empty. Invalid CLI/placement inputs exit 2, missing
resources 4, typed ambiguities 5, authentication/permission errors 6 and
API/network errors 7. Malformed model data or unexpected failures exit 1.
SDK errors retain their type, status and operation/request IDs while normal
provider messages are replaced with a generic diagnostic. Usage diagnostics
use stderr text; API/internal diagnostics follow the existing JSON/table error
contract. Explicit debug traces may expose original exception data.

## Resolution limits

The resolver checks the selected service plan in the provisioning context,
the requested root size against reported plan capacity, and available network
zone/group/pool references when a private network is supplied. Group, zone
and instance-type name/code lookups traverse all pages and reject duplicate
matches; duplicate named layouts and pools also fail.

This is not a provider-side validation request. Numeric pool/layout IDs are
passed through by the SDK, and missing network ownership metadata is not
proof of compatibility. External-network access, security-group existence,
minimum image disk requirements, quotas, permissions for creation, available
capacity and eventual provisioning success are not established. Discovery
does not reserve resources or capture an atomic snapshot; rerun before a
subsequent provisioning operation.

## Live verification

Set `MTN_CLOUD_TEST_GROUP_ID`, `MTN_CLOUD_TEST_ZONE_ID`,
`MTN_CLOUD_TEST_POOL_ID`, `MTN_CLOUD_TEST_LAYOUT_ID`,
`MTN_CLOUD_TEST_PLAN_ID` to positive numeric IDs, and
`MTN_CLOUD_TEST_INSTANCE_TYPE_CODE` to an existing type code. Optionally set
`MTN_CLOUD_TEST_NETWORK_ID` to check a compatible private network.

```bash
MTN_CLOUD_RUN_LIVE_TESTS=1 uv run pytest \
  tests/integration/test_live_cli_plan.py -q -x --tb=short
```

The suite authenticates first and checks the JSON envelope and resolved
selections, requesting a one-GiB root size for discovery only. Missing test
selectors skip this test. No creation, waiter or cleanup is performed, and
success does not establish a provisioning lifecycle contract.
