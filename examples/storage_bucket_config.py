"""Create an S3-compatible MTN Cloud storage-bucket configuration.

The SDK manages the MTN Cloud control-plane configuration. Object data-plane
operations require a separate S3-compatible client and are not performed here.

Example::

    export MTN_CLOUD_TOKEN="your-token"
    export MTN_S3_ACCESS_KEY="your-access-key"
    export MTN_S3_SECRET_KEY="your-secret-key"
    uv run python examples/storage_bucket_config.py --name backups \
        --bucket-name hexcore-backups --endpoint https://s3.example.ng:9021
"""

from __future__ import annotations

import argparse
import os

from mtn_cloud import MtnCloudClient, MtnCloudError
from mtn_cloud.models.storage_bucket import StorageBucketCreate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="MTN Cloud configuration name.")
    parser.add_argument("--bucket-name", required=True, help="S3 bucket name.")
    parser.add_argument("--endpoint", required=True, help="S3-compatible endpoint.")
    parser.add_argument("--create-bucket", action="store_true")
    args = parser.parse_args()

    access_key = os.getenv("MTN_S3_ACCESS_KEY", "").strip()
    secret_key = os.getenv("MTN_S3_SECRET_KEY", "").strip()
    if not access_key or not secret_key:
        raise SystemExit("Set MTN_S3_ACCESS_KEY and MTN_S3_SECRET_KEY before running.")

    request = StorageBucketCreate(
        name=args.name,
        bucket_name=args.bucket_name,
        config={
            "accessKey": access_key,
            "secretKey": secret_key,
            "endpoint": args.endpoint,
        },
        create_bucket=args.create_bucket,
    )
    try:
        with MtnCloudClient() as cloud:
            bucket = cloud.storage_buckets.create(request)
            print(f"Created storage configuration {bucket.id}: {bucket.name}")
    except MtnCloudError as exc:
        raise SystemExit(f"Storage configuration failed: {exc}") from exc


if __name__ == "__main__":
    main()
