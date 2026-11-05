"""Resolve and optionally provision an instance with the modern SDK.

The default mode is a dry run. Use ``--apply`` only when you intend to create
an instance and wait for it to become ready::

    export MTN_CLOUD_TOKEN="your-token"
    uv run python examples/create_instance.py --group Production \
        --type-code MTN-CS10 --plan G1S1
    uv run python examples/create_instance.py --group Production \
        --type-code MTN-CS10 --plan G1S1 --apply
"""

from __future__ import annotations

import argparse

from mtn_cloud import MtnCloudClient, MtnCloudError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="sdk-example-01")
    parser.add_argument("--group", required=True, help="Group name or numeric ID.")
    parser.add_argument("--type-code", required=True, help="Instance type code.")
    parser.add_argument("--plan", required=True, help="Plan name, code, or ID.")
    parser.add_argument("--zone", help="Optional zone name or numeric ID.")
    parser.add_argument("--resource-pool", help="Optional pool name, code, or ID.")
    parser.add_argument("--network-id", help="Optional private network ID.")
    parser.add_argument("--apply", action="store_true", help="Actually create the instance.")
    args = parser.parse_args()

    try:
        with MtnCloudClient() as cloud:
            result = cloud.instances.provision(
                args.name,
                type_code=args.type_code,
                group=args.group,
                plan=args.plan,
                zone=args.zone,
                resource_pool=args.resource_pool,
                network_id=args.network_id,
                dry_run=not args.apply,
                wait=args.apply,
            )
            if isinstance(result, dict):
                print("Dry-run resolution:")
                for key, value in result.items():
                    print(f"  {key}: {value}")
            else:
                print(f"Instance ready: {result.id} ({result.name})")
                print(f"Status: {result.status}; primary IP: {result.primary_ip or 'none'}")
    except (ValueError, MtnCloudError) as exc:
        raise SystemExit(f"Provisioning failed: {exc}") from exc


if __name__ == "__main__":
    main()
