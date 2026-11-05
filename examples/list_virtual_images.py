"""List image metadata without retrieving or printing image user-data.

Run from the repository root with credentials in the environment or .env::

    uv run python examples/list_virtual_images.py --image-type qcow2
    uv run python examples/list_virtual_images.py --filter-type Synced
"""

import argparse

from mtn_cloud import MtnCloudClient, MtnCloudError


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover virtual-image metadata (GET only).")
    parser.add_argument("--name", help="Filter by image name")
    parser.add_argument("--image-type", help="Image format/provider code, such as qcow2")
    parser.add_argument("--filter-type", choices=("User", "System", "Synced", "All"))
    args = parser.parse_args()
    try:
        with MtnCloudClient() as cloud:
            images = cloud.virtual_images.list_all(
                name=args.name, image_type=args.image_type, filter_type=args.filter_type
            )
            for image in images:
                print(image.id, image.name, image.image_type, image.visibility or "unknown")
            print(f"Images: {len(images)}")
    except MtnCloudError as exc:
        print(f"Image discovery failed: {type(exc).__name__}; HTTP status={exc.status_code}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
