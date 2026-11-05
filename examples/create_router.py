"""Create, verify, and optionally remove an MTN neutron router.

This is a mutating example. It requires ``--apply`` and supports
``--delete-after`` for demonstrations with explicit cleanup.
"""

from __future__ import annotations

import argparse
import json

from mtn_cloud import MtnCloudClient, MtnCloudError
from mtn_cloud.models.router import RouterCreate


def _resource_id(value: str) -> int | None:
    return int(value) if value.isascii() and value.isdigit() else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True, help="Group name or numeric ID.")
    parser.add_argument("--zone", required=True, help="Zone name or numeric ID.")
    parser.add_argument("--resource-pool", required=True, help="Pool name, code, or ID.")
    parser.add_argument("--internal-subnet", action="append", type=int, required=True)
    parser.add_argument("--external-network", help="External network name or ID.")
    parser.add_argument("--name", default="sdk-example-router")
    parser.add_argument("--apply", action="store_true", help="Actually create the router.")
    parser.add_argument("--delete-after", action="store_true")
    args = parser.parse_args()

    if args.delete_after and not args.apply:
        parser.error("--delete-after requires --apply")
    if not args.apply:
        print("Dry run only: pass --apply to create the router.")
        return

    router_id: int | None = None
    try:
        with MtnCloudClient() as cloud:
            group = (
                cloud.groups.get(int(args.group))
                if _resource_id(args.group) is not None
                else cloud.groups.get_by_name(args.group)
            )
            zone = (
                cloud.zones.get(int(args.zone))
                if _resource_id(args.zone) is not None
                else cloud.zones.get_by_name(args.zone)
            )
            pools = cloud.resource_pools.list(zone_id=zone.id, group_id=group.id)
            pool_matches = [
                pool
                for pool in pools
                if args.resource_pool in {pool.code, pool.name or ""}
                or _resource_id(args.resource_pool) == pool.id
            ]
            if len(pool_matches) != 1:
                raise ValueError(f"Resource pool '{args.resource_pool}' was not uniquely found")
            pool = pool_matches[0]

            external_id = None
            if args.external_network:
                external = cloud.routers.list_external_networks(
                    zone_id=zone.id,
                    group_id=group.id,
                    resource_pool_code=pool.code,
                )
                matches = [
                    item
                    for item in external
                    if item.name == args.external_network or str(item.id) == args.external_network
                ]
                if len(matches) != 1:
                    raise ValueError(
                        f"External network '{args.external_network}' was not uniquely found"
                    )
                external_id = matches[0].id

            router = cloud.routers.create(
                RouterCreate(
                    name=args.name,
                    group_id=group.id,
                    cloud_id=zone.id,
                    resource_pool_id=pool.id,
                    internal_subnet_ids=args.internal_subnet,
                    external_network_id=external_id,
                ),
                wait=False,
            )
            router_id = router.id
            print(f"Submitted router: {router_id}", flush=True)
            router = cloud.routers.wait_until_ready(router_id)
            print(json.dumps({"id": router.id, "name": router.name, "status": router.status}))
    except MtnCloudError as exc:
        if router_id is None and exc.response:
            submitted_id = exc.response.get("router_id")
            if type(submitted_id) is int and submitted_id > 0:
                router_id = submitted_id
        raise SystemExit(f"Router operation failed: {exc}") from exc
    except ValueError as exc:
        raise SystemExit(f"Router operation failed: {exc}") from exc
    finally:
        if args.delete_after and router_id is not None:
            with MtnCloudClient() as cloud:
                cloud.routers.delete(router_id)
                cloud.routers.wait_until_deleted(router_id)
            print(f"Deleted router {router_id}")


if __name__ == "__main__":
    main()
