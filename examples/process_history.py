"""Inspect existing operation history without printing process logs.

Run with configured credentials from the repository root::

    uv run python examples/process_history.py --process-id 901 --instance-id 100
    uv run python examples/process_history.py --instance-id 100

Polling requires an explicit status label verified for your environment::

    uv run python examples/process_history.py --process-id 901 \
        --wait-for-status complete --failure-status failed
"""

import argparse

from mtn_cloud import MtnCloudClient, MtnCloudError


def main() -> int:
    parser = argparse.ArgumentParser(description="Read process metadata (GET only).")
    parser.add_argument("--process-id", type=int)
    parser.add_argument("--instance-id", type=int)
    parser.add_argument(
        "--wait-for-status", help="Explicit status to wait for; no default mapping."
    )
    parser.add_argument("--failure-status", action="append", default=[])
    args = parser.parse_args()
    if args.process_id is None and args.instance_id is None:
        parser.error("provide --process-id or --instance-id")
    if any(value is not None and value <= 0 for value in (args.process_id, args.instance_id)):
        parser.error("IDs must be positive")
    if (args.wait_for_status is not None or args.failure_status) and args.process_id is None:
        parser.error("polling requires --process-id")
    if args.failure_status and args.wait_for_status is None:
        parser.error("--failure-status requires --wait-for-status")
    try:
        with MtnCloudClient() as cloud:
            if args.process_id is not None:
                if args.wait_for_status is not None:
                    process = cloud.processes.wait_for_status(
                        args.process_id,
                        args.wait_for_status,
                        instance_id=args.instance_id,
                        failure_statuses=args.failure_status,
                    )
                else:
                    process = cloud.processes.get(args.process_id, instance_id=args.instance_id)
                print(process.id, process.status, process.percent)
            else:
                page = cloud.processes.list_page(instance_id=args.instance_id)
                for process in page.items:
                    print(process.id, process.status, process.percent)
                print(f"Returned: {len(page.items)}; provider total: {page.total}")
    except (MtnCloudError, ValueError) as exc:
        print(f"Process inspection failed: {type(exc).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
