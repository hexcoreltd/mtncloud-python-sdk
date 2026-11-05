"""Read-only SDK tour.

Run with::

    export MTN_CLOUD_TOKEN="your-token"
    uv run python examples/basic_usage.py

This example performs discovery only.
"""

from mtn_cloud import MtnCloudClient, MtnCloudError


def main() -> None:
    try:
        with MtnCloudClient() as cloud:
            user = cloud.whoami()
            print(f"Authenticated as {user.username}")

            groups = cloud.groups.list(limit=10)
            print(f"Groups: {len(groups)}")
            for group in groups:
                print(f"  - {group.id}: {group.name}")

            instances = cloud.instances.list(limit=10)
            print(f"Instances: {len(instances)}")
            for instance in instances:
                print(f"  - {instance.id}: {instance.name} ({instance.status})")

            networks = cloud.networks.list(limit=10)
            print(f"Networks: {len(networks)}")
            for network in networks:
                print(f"  - {network.id}: {network.name} ({network.cidr or 'no CIDR'})")
    except MtnCloudError as exc:
        print(f"MTN Cloud request failed: {exc}")


if __name__ == "__main__":
    main()
