"""Focused, opt-in networking contract checks against a real tenant.

Tests not marked ``mutation`` perform GET requests only. A failed connection or permission check
is a failure, not a skip; empty tenant collections skip only detail checks.
"""

import os
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.models.network import NetworkCreate
from mtn_cloud.models.router import RouterCreate
from mtn_cloud.modern_exceptions import MtnCloudError, NotFoundError


@pytest.fixture(scope="module")
def networking_client() -> Iterator[MtnCloudClient]:
    if os.getenv("MTN_CLOUD_RUN_LIVE_TESTS", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("set MTN_CLOUD_RUN_LIVE_TESTS=1 to run live networking tests")
    settings = ClientSettings(timeout=10, max_retries=0)
    if not settings.token_value():
        pytest.fail("Live networking tests require MTN_CLOUD_TOKEN or MTN_CLOUD_API_KEY")
    with MtnCloudClient(settings=settings) as client:
        failure = None
        try:
            client.whoami()
        except MtnCloudError as exc:
            # HTTP bodies can contain tenant data or intermediary HTML. Keep
            # diagnostics to operation metadata rather than printing payloads.
            failure = (
                f"Live authentication preflight failed: {type(exc).__name__}; "
                f"status={exc.status_code}; method={exc.method}; path={exc.path}"
            )
        if failure is not None:
            # Fail outside the exception handler so pytest does not display
            # the original HTTP exception and its potentially sensitive body.
            pytest.fail(failure, pytrace=False)
        yield client


@pytest.mark.parametrize(
    ("path", "collection_key", "model_name"),
    [
        ("/networks", "networks", "networks"),
        ("/networks/routers", "networkRouters", "routers"),
    ],
)
def test_live_network_collection_and_detail(
    networking_client: MtnCloudClient, path: str, collection_key: str, model_name: str
) -> None:
    """Check the raw collection envelope and parse a real detail response."""
    body = networking_client._core.request("GET", path, params={"max": 5, "offset": 0})
    assert isinstance(body, dict), "Expected a JSON object collection envelope"
    assert isinstance(body.get(collection_key), list), "Expected a resource collection"
    items = body[collection_key]
    if not items:
        pytest.skip(f"Collection {collection_key} is empty; detail contract was not exercised")
    resource_id = items[0].get("id")
    assert type(resource_id) is int and resource_id > 0, "Expected a positive resource ID"
    service: Any = getattr(networking_client, model_name)
    detail = service.get(resource_id)
    assert detail.id == resource_id


def test_live_subnet_parent_contract(networking_client: MtnCloudClient) -> None:
    """Check raw parent references as well as the SDK's subnet adapter."""
    networks = networking_client.networks.list(limit=5)
    if not networks:
        pytest.skip("No network available; subnet contract was not exercised")
    network_id = networks[0].id
    body = networking_client._core.request("GET", f"/networks/{network_id}/subnets")
    assert isinstance(body, dict) and isinstance(body.get("subnets"), list)
    for subnet in body["subnets"]:
        parent = subnet.get("network")
        if parent is not None:
            assert isinstance(parent, dict) and parent.get("id") == network_id
    parsed = networking_client.networks.list_subnets(network_id)
    assert all(subnet.network_id in (None, network_id) for subnet in parsed)


def test_live_router_interface_contract(networking_client: MtnCloudClient) -> None:
    """Exercise the embedded interface contract on an existing router."""
    routers = networking_client.routers.list(limit=5)
    if not routers:
        pytest.skip("No router available; interface contract was not exercised")
    router_id = routers[0].id
    body = networking_client._core.request("GET", f"/networks/routers/{router_id}")
    assert isinstance(body, dict) and isinstance(body.get("networkRouter"), dict)
    raw_interfaces = body["networkRouter"].get("interfaces")
    assert isinstance(raw_interfaces, list), "Expected an embedded interfaces collection"
    parsed = networking_client.routers.model.model_validate(body["networkRouter"])
    assert len(parsed.interfaces) == len(raw_interfaces)
    for raw, interface in zip(raw_interfaces, parsed.interfaces, strict=True):
        assert isinstance(raw, dict)
        reference = raw.get("networkSubnet")
        if reference is not None:
            assert isinstance(reference, dict) and type(reference.get("id")) is int
            assert interface.subnet_id == reference["id"]
        else:
            assert interface.subnet_id is None


@pytest.mark.mutation
def test_live_router_create_wait_delete(networking_client: MtnCloudClient) -> None:
    """Run on a dedicated, unattached test subnet supplied by the operator."""
    if os.getenv("MTN_CLOUD_ALLOW_MUTATIONS", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("set MTN_CLOUD_ALLOW_MUTATIONS=1 to run router lifecycle tests")
    fields = {
        "group_id": "MTN_CLOUD_TEST_GROUP_ID",
        "cloud_id": "MTN_CLOUD_TEST_ZONE_ID",
        "resource_pool_id": "MTN_CLOUD_TEST_POOL_ID",
        "subnet_id": "MTN_CLOUD_TEST_ROUTER_SUBNET_ID",
    }
    ids: dict[str, int] = {}
    for field, variable in fields.items():
        raw = os.getenv(variable, "")
        if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
            pytest.fail(f"Set {variable} to a positive test resource ID before mutation")
        ids[field] = int(raw)

    router_id = None
    try:
        router = networking_client.routers.create(
            RouterCreate(
                name=f"sdk-router-contract-{uuid4().hex[:12]}",
                group_id=ids["group_id"],
                cloud_id=ids["cloud_id"],
                resource_pool_id=ids["resource_pool_id"],
                internal_subnet_ids=[ids["subnet_id"]],
            )
        )
        router_id = router.id
        ready = networking_client.routers.wait_until_ready(router_id, timeout=600)
        assert ready.external_id, "Router lacks a backend resource ID"
        assert ready.type is not None and ready.type.code == "neutronRouter"
        assert ready.interfaces, "Router lacks the requested internal interface"
    except MtnCloudError as exc:
        if router_id is None:
            candidate = (exc.response or {}).get("router_id")
            if type(candidate) is int and candidate > 0:
                router_id = candidate
        raise
    finally:
        if router_id is not None:
            networking_client.routers.delete(router_id)
            networking_client.routers.wait_until_deleted(router_id, timeout=600)


def test_live_network_create_preflight(networking_client: MtnCloudClient) -> None:
    """Validate explicitly selected placement with GET requests only."""
    variables = {
        "group_id": "MTN_CLOUD_TEST_GROUP_ID",
        "cloud_id": "MTN_CLOUD_TEST_ZONE_ID",
        "resource_pool_id": "MTN_CLOUD_TEST_POOL_ID",
        "type_id": "MTN_CLOUD_TEST_NETWORK_TYPE_ID",
    }
    ids: dict[str, int] = {}
    for field, variable in variables.items():
        raw = os.getenv(variable)
        if raw is None:
            pytest.skip(f"Set {variable} to exercise network placement validation")
        if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
            pytest.fail(f"{variable} must be a positive resource ID")
        ids[field] = int(raw)
    networking_client.networks.validate_create(
        NetworkCreate(
            name="sdk-preflight-only",
            group_id=ids["group_id"],
            cloud_id=ids["cloud_id"],
            resource_pool_id=ids["resource_pool_id"],
            type_id=ids["type_id"],
            cidr="192.0.2.0/24",
            gateway="192.0.2.1",
        )
    )


def _mutation_ids(variables: dict[str, str]) -> dict[str, int]:
    ids: dict[str, int] = {}
    for field, variable in variables.items():
        raw = os.getenv(variable, "")
        if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
            pytest.fail(f"Set {variable} to a positive test resource ID before mutation")
        ids[field] = int(raw)
    return ids


def _wait_until_absent(fetch: Any, timeout: float = 600, interval: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            fetch()
        except NotFoundError:
            return
        if time.monotonic() >= deadline:
            pytest.fail("Resource still present after deletion timeout", pytrace=False)
        time.sleep(interval)


@pytest.mark.mutation
def test_live_network_and_router_lifecycle() -> None:
    """Create a throwaway network, attach a router to its subnet, then remove both.

    Requires MTN_CLOUD_RUN_LIVE_TESTS=1 and MTN_CLOUD_ALLOW_MUTATIONS=1. The
    CIDR defaults to 10.254.254.0/24; override MTN_CLOUD_TEST_NETWORK_CIDR if
    that range is in use. Cleanup runs in reverse order even when a step fails,
    and also looks the network up by its unique name in case creation timed out.
    """
    if os.getenv("MTN_CLOUD_RUN_LIVE_TESTS", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("set MTN_CLOUD_RUN_LIVE_TESTS=1 to run live networking tests")
    if os.getenv("MTN_CLOUD_ALLOW_MUTATIONS", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("set MTN_CLOUD_ALLOW_MUTATIONS=1 to run network and router lifecycle tests")
    ids = _mutation_ids(
        {
            "group_id": "MTN_CLOUD_TEST_GROUP_ID",
            "cloud_id": "MTN_CLOUD_TEST_ZONE_ID",
            "resource_pool_id": "MTN_CLOUD_TEST_POOL_ID",
            "type_id": "MTN_CLOUD_TEST_NETWORK_TYPE_ID",
        }
    )
    cidr = os.getenv("MTN_CLOUD_TEST_NETWORK_CIDR", "10.254.254.0/24")
    gateway = cidr.rsplit(".", 1)[0] + ".1"
    name = f"sdk-network-contract-{uuid4().hex[:12]}"
    router_name = f"sdk-router-contract-{uuid4().hex[:12]}"

    with MtnCloudClient(settings=ClientSettings(timeout=60, max_retries=2)) as client:
        network_id: int | None = None
        router_id: int | None = None
        try:
            network = client.networks.create(
                NetworkCreate(
                    name=name,
                    group_id=ids["group_id"],
                    cloud_id=ids["cloud_id"],
                    resource_pool_id=ids["resource_pool_id"],
                    type_id=ids["type_id"],
                    cidr=cidr,
                    gateway=gateway,
                ),
                validate=True,
            )
            network_id = network.id
            assert network.name == name

            # Only a subnet that names this network as its parent and carries the
            # requested CIDR is safe to attach; MTN can briefly return another
            # network's subnet for a new network.
            own: list[Any] = []
            deadline = time.monotonic() + 300
            while not own and time.monotonic() < deadline:
                own = [
                    subnet
                    for subnet in client.networks.list_subnets(network_id)
                    if subnet.network_id == network_id and subnet.cidr == cidr
                ]
                if not own:
                    time.sleep(10)
            assert len(own) == 1, "Network creation produced no matching subnet within 300 seconds"

            router = client.routers.create(
                RouterCreate(
                    name=router_name,
                    group_id=ids["group_id"],
                    cloud_id=ids["cloud_id"],
                    resource_pool_id=ids["resource_pool_id"],
                    internal_subnet_ids=[own[0].id],
                )
            )
            router_id = router.id
            ready = client.routers.wait_until_ready(router_id, timeout=600)
            assert ready.type is not None and ready.type.code == "neutronRouter"
            # MTN router interfaces reference the network and CIDR, not the
            # subnet (observed 2026-11-05), so match on those.
            assert any(
                i.network is not None and i.network.id == network_id and i.cidr == cidr
                for i in ready.interfaces
            ), "Router lacks an interface on the test network"
        except MtnCloudError as exc:
            if router_id is None:
                candidate = (exc.response or {}).get("router_id")
                if type(candidate) is int and candidate > 0:
                    router_id = candidate
            raise
        finally:
            # Each step runs even if an earlier one fails; the first cleanup
            # error is re-raised at the end. Names are unique per run, so every
            # name match belongs to this test.
            failures: list[BaseException] = []
            router_ids = {router_id} if router_id is not None else set()
            try:
                router_ids |= {
                    r.id for r in client.routers.list(name=router_name) if r.name == router_name
                }
            except Exception as exc:
                failures.append(exc)
            for rid in router_ids:
                try:
                    client.routers.delete(rid)
                    client.routers.wait_until_deleted(rid, timeout=600)
                except Exception as exc:
                    failures.append(exc)
            network_ids = {network_id} if network_id is not None else set()
            try:
                network_ids |= {n.id for n in client.networks.list(name=name) if n.name == name}
            except Exception as exc:
                failures.append(exc)
            for nid in network_ids:
                try:
                    client.networks.delete(nid)
                    _wait_until_absent(lambda nid=nid: client.networks.get(nid))
                except BaseException as exc:
                    failures.append(exc)
            if failures:
                raise failures[0]
