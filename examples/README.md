# Examples

These examples target the modern `MtnCloudClient` API and are intended to be
run from the repository root with `uv`:

```bash
uv sync --locked --extra dev
uv run python examples/basic_usage.py
```

Available examples:

- `basic_usage.py` — authenticated, read-only resource discovery.
- `list_virtual_images.py` — read-only image metadata discovery with optional
  name, format and origin filters, without printing user-data or provider details.
- `list_snapshots.py` — read-only instance snapshot inventory using an explicit
  instance ID; prints selected metadata without file/provider details.
- `create_instance.py` — safe provisioning resolution with dry-run as the
  default; pass `--apply` to create an instance.
- `create_router.py` — explicit router creation with optional cleanup through
  `--delete-after`.
- `list_storage_buckets.py` — storage configuration and unattached-volume
  discovery without printing credentials.
- `storage_bucket_config.py` — create an S3-compatible control-plane bucket
  configuration; object data-plane operations require a separate S3 client.
- `cli_inventory.py` — invoke the read-only `mtncloud inventory` command from
  Python.

All examples read credentials from environment variables and avoid committing
secrets. Mutating examples require an explicit flag. Confirm resource IDs,
permissions, costs, and cleanup behavior before running them against a live
tenant.

For a read-only provisioning summary from the CLI, use:

```bash
uv run mtncloud plan --name api-01 --type-code MTN-CS10 \
  --group production --plan G1S1 -o json
```

Use your tenant's selections. See [CLI planning](../docs/cli-planning.md) for
the output contract and the limits of discovery before provisioning.
