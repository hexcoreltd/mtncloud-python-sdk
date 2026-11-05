"""Opt-in planning with explicit existing placement IDs; no creation or cleanup."""

import json
import os

import pytest

from mtn_cloud import MtnCloudClient


def test_live_cli_instance_plan(
    authenticated_client: MtnCloudClient, capsys: pytest.CaptureFixture[str]
) -> None:
    from mtn_cloud.cli import main

    selectors = {
        "--group": os.getenv("MTN_CLOUD_TEST_GROUP_ID"),
        "--zone": os.getenv("MTN_CLOUD_TEST_ZONE_ID"),
        "--resource-pool": os.getenv("MTN_CLOUD_TEST_POOL_ID"),
        "--layout": os.getenv("MTN_CLOUD_TEST_LAYOUT_ID"),
        "--plan": os.getenv("MTN_CLOUD_TEST_PLAN_ID"),
        "--type-code": os.getenv("MTN_CLOUD_TEST_INSTANCE_TYPE_CODE"),
    }
    if not all(selectors.values()):
        pytest.skip("Configure all CLI plan test selectors; see docs/cli-planning.md")
    args = ["plan", "--name", "sdk-live-plan-only", "-o", "json"]
    for option, value in selectors.items():
        assert value is not None
        args.extend((option, value))
    # A one-GiB request avoids assuming the selected plan includes ten GiB.
    args.extend(("--root-volume-size-gb", "1"))
    network = os.getenv("MTN_CLOUD_TEST_NETWORK_ID")
    if network:
        args.extend(("--network-id", network))
    assert main(args, client_factory=lambda settings: authenticated_client) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["schema"] == "mtncloud.plan/v1" and document["dry_run"] is True
    resolved = document["resolved"]
    for field, option in (
        ("group_id", "--group"),
        ("zone_id", "--zone"),
        ("layout", "--layout"),
        ("plan", "--plan"),
    ):
        assert resolved[field] == int(selectors[option] or "0")
    assert resolved["type"] == selectors["--type-code"]
    assert resolved["resource_pool_id"] == f"pool-{selectors['--resource-pool']}"
