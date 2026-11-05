"""Inspect existing instance snapshots using GET requests only.

Run from the repository root with configured credentials::

    uv run python examples/list_snapshots.py --instance-id 100
"""

import argparse

from mtn_cloud import MtnCloudClient, MtnCloudError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List snapshot metadata without modifying resources."
    )
    parser.add_argument("--instance-id", required=True, type=int)
    args = parser.parse_args()
    if args.instance_id <= 0:
        parser.error("--instance-id must be positive")
    try:
        with MtnCloudClient() as cloud:
            for snapshot in cloud.instances.list_snapshots(args.instance_id):
                print(snapshot.id, snapshot.name, snapshot.status, snapshot.snapshot_created)
    except (MtnCloudError, ValueError) as exc:
        print(f"Snapshot discovery failed: {type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
