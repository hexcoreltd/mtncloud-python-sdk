"""Inspect modern storage resources without exposing bucket credentials."""

from mtn_cloud import MtnCloudClient, MtnCloudError


def main() -> None:
    try:
        with MtnCloudClient() as cloud:
            buckets = cloud.storage_buckets.list()
            print(f"Storage bucket configurations: {len(buckets)}")
            for bucket in buckets:
                print(
                    f"  - {bucket.id}: {bucket.name} "
                    f"provider={bucket.provider_type} bucket={bucket.bucket_name}"
                )

            volumes = cloud.volumes.list_unattached()
            print(f"Unattached volumes: {len(volumes)}")
            for volume in volumes:
                print(f"  - {volume.id}: {volume.name} ({volume.status or 'unknown'})")
    except MtnCloudError as exc:
        raise SystemExit(f"Storage discovery failed: {exc}") from exc


if __name__ == "__main__":
    main()
