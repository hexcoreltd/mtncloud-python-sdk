"""Modern service for MTN Cloud routers and external networks."""

from __future__ import annotations

import time
from collections.abc import Callable
from math import isfinite
from typing import Any, List

from pydantic import ValidationError as ModelValidationError

from mtn_cloud.core import CoreClient
from mtn_cloud.models.router import ExternalNetwork, Router, RouterCreate, RouterInterface
from mtn_cloud.modern_exceptions import (
    AmbiguousLookupError,
    ForbiddenError,
    LookupNotFoundError,
    MtnCloudError,
    NotFoundError,
    TimeoutError,
)
from mtn_cloud.services.base import Page, Service
from mtn_cloud.services.networks import NetworksService


class RoutersService(Service[Router]):
    """Discover and manage MTN neutron routers."""

    path = "/networks/routers"
    item_key = "networkRouter"
    list_key = "networkRouters"
    model = Router

    def __init__(
        self,
        core: CoreClient,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(core)
        self._sleeper = sleeper
        self._clock = clock

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
        zone_id: int | None = None,
        group_id: int | None = None,
    ) -> Page[Router]:
        params: dict[str, Any] = {
            "max": limit,
            "offset": offset,
            "name": name,
            "zoneId": zone_id,
            "siteId": group_id,
        }
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[Router]:
        return self.list_page(**kwargs).items

    def get(self, router_id: int) -> Router:
        return self._get(router_id)

    def get_by_name(
        self, name: str, *, zone_id: int | None = None, group_id: int | None = None
    ) -> Router:
        """Return the uniquely named router, optionally scoped by zone or group."""

        return self._get_by_name("Router", name, zone_id=zone_id, group_id=group_id)

    def list_interfaces(self, router_id: int) -> List[RouterInterface]:
        """List the interfaces attached to a router."""

        return self.get(router_id).interfaces

    def get_interface(self, router_id: int, subnet_id: int) -> RouterInterface:
        """Return the interface attached to a subnet.

        Interfaces are currently exposed as part of the router resource, so
        this helper deliberately uses router retrieval instead of assuming a
        separate undocumented interface endpoint.

        MTN Cloud interfaces carry a ``network`` reference and ``cidr`` but no
        subnet reference. When no interface names the subnet directly, each
        such interface's network is checked for the subnet, and an interface
        matches only if it is on that network and has the subnet's CIDR.
        The subnet must name that network as its parent. Networks that return
        404, such as a router's external gateway network, are skipped; a 403 is
        raised if no interface matched, so a permission problem is not reported
        as a missing interface.
        """

        interfaces = self.list_interfaces(router_id)
        matches = [interface for interface in interfaces if interface.subnet_id == subnet_id]
        if not matches:
            matches = self._match_by_parent_network(interfaces, subnet_id)
        if not matches:
            raise LookupNotFoundError(f"Router {router_id} has no interface for subnet {subnet_id}")
        if len(matches) > 1:
            raise AmbiguousLookupError(
                f"Router {router_id} has multiple interfaces for subnet {subnet_id}"
            )
        return matches[0]

    def _match_by_parent_network(
        self, interfaces: List[RouterInterface], subnet_id: int
    ) -> List[RouterInterface]:
        unreferenced = [
            interface
            for interface in interfaces
            if interface.subnet_id is None and interface.network is not None
        ]
        networks = NetworksService(self._core)
        denied: ForbiddenError | None = None
        for network_id in sorted({i.network.id for i in unreferenced if i.network is not None}):
            try:
                candidates = networks.list_subnets(network_id)
            except NotFoundError:
                # Gateway interfaces sit on provider networks the tenant cannot
                # read; the requested subnet cannot be identified there.
                continue
            except ForbiddenError as exc:
                denied = denied or exc
                continue
            subnet = next(
                (s for s in candidates if s.id == subnet_id and s.network_id == network_id),
                None,
            )
            if subnet is None:
                continue
            return [
                interface
                for interface in unreferenced
                if interface.network is not None
                and interface.network.id == network_id
                and subnet.cidr is not None
                and interface.cidr == subnet.cidr
            ]
        if denied is not None:
            # A permission problem must not read as "no interface for subnet".
            raise denied
        return []

    def list_types(self, *, limit: int = 100, offset: int = 0) -> List[dict[str, Any]]:
        """List router types exposed by the control plane."""

        body = self._core.request(
            "GET",
            "/network-router-types",
            params={"max": limit, "offset": offset},
        )
        if not isinstance(body, dict) or not isinstance(body.get("networkRouterTypes"), list):
            raise MtnCloudError("Invalid router-type response")
        return [item for item in body["networkRouterTypes"] if isinstance(item, dict)]

    def neutron_router_type_id(self) -> int:
        """Resolve and validate the creatable MTN neutron router type."""

        matches = [item for item in self.list_types() if item.get("code") == "neutronRouter"]
        if len(matches) != 1:
            raise ValueError("Expected exactly one available MTN neutronRouter type")
        type_id = matches[0].get("id")
        if type(type_id) is not int or type_id <= 0:
            raise ValueError("MTN neutronRouter type did not contain a valid ID")
        body = self._core.request("GET", f"/network-router-types/{type_id}")
        detail = body.get("networkRouterType", body) if isinstance(body, dict) else {}
        if (
            not isinstance(detail, dict)
            or detail.get("code") != "neutronRouter"
            or not detail.get("creatable")
            or detail.get("hasNetworkServer")
        ):
            raise ValueError("The MTN neutronRouter type is not available for creation")
        return type_id

    def list_external_networks(
        self,
        *,
        zone_id: int,
        group_id: int,
        resource_pool_code: str,
        router_type_id: int | None = None,
    ) -> List[ExternalNetwork]:
        """List external gateway options for a router placement scope."""

        type_id = router_type_id or self.neutron_router_type_id()
        body = self._core.request(
            "GET",
            "/options/openstackExternalNetworks",
            params={
                "router.zone.id": zone_id,
                "router.site.id": group_id,
                "router.poolId": resource_pool_code,
                "routerType.id": type_id,
            },
        )
        if not isinstance(body, dict) or body.get("success") is False:
            raise MtnCloudError("External-network discovery failed", response=body)
        if not isinstance(body.get("data"), list):
            raise MtnCloudError("Invalid external-network response")
        return [ExternalNetwork.model_validate(item) for item in body["data"]]

    def create(
        self,
        request: RouterCreate,
        *,
        router_type_id: int | None = None,
        wait: bool = False,
        timeout: float = 300,
        poll_interval: float = 5,
    ) -> Router:
        """Create a router, preserving its submitted ID on follow-up errors.

        When a read or waiter fails after a successful POST, the exception's
        ``response["router_id"]`` identifies the resource to inspect or clean up.
        A failed POST is never automatically resubmitted.
        """

        if wait:
            self._validate_wait_options(timeout, poll_interval)
        type_id = router_type_id or self.neutron_router_type_id()
        body = self._core.request(
            "POST",
            self.path,
            json=request.to_api_payload(type_id),
        )
        if not isinstance(body, dict) or body.get("success") is not True:
            raise MtnCloudError("Router creation did not return success", response=body)
        router_id = body.get("id")
        if type(router_id) is not int or router_id <= 0:
            raise MtnCloudError("Router creation did not return a valid ID", response=body)
        router = self._get_with_context(router_id)
        return (
            self.wait_until_ready(router.id, timeout=timeout, poll_interval=poll_interval)
            if wait
            else router
        )

    def delete(self, router_id: int) -> bool:
        """Submit deletion; an already absent router is considered success.

        Use ``wait_until_deleted`` to confirm asynchronous removal.
        """

        try:
            router = self._get_with_context(router_id)
        except NotFoundError:
            return True
        if router.type is None or router.type.code != "neutronRouter":
            raise ValueError(f"Router {router_id} is not an MTN neutronRouter")
        try:
            body = self._core.request("DELETE", f"{self.path}/{router_id}")
        except NotFoundError:
            # Another actor may have removed it since the preceding GET.
            return True
        except MtnCloudError as exc:
            exc.response = {**(exc.response or {}), "router_id": router_id}
            raise
        if isinstance(body, dict) and body.get("success") is False:
            raise MtnCloudError(
                f"Router {router_id} deletion was rejected",
                response={**body, "router_id": router_id},
            )
        return True

    @staticmethod
    def _validate_wait_options(timeout: float, poll_interval: float) -> None:
        if (
            not isfinite(timeout)
            or not isfinite(poll_interval)
            or timeout <= 0
            or poll_interval <= 0
        ):
            raise ValueError("timeout and poll_interval must be finite and positive")

    def _get_with_context(self, router_id: int) -> Router:
        """Keep the cleanup ID even when a detail read cannot be parsed."""
        try:
            return self.get(router_id)
        except MtnCloudError as exc:
            exc.response = {**(exc.response or {}), "router_id": router_id}
            raise
        except ModelValidationError as exc:
            raise MtnCloudError(
                f"Router {router_id} returned an invalid detail response",
                response={"router_id": router_id},
            ) from exc

    def wait_until_ready(
        self,
        router_id: int,
        *,
        timeout: float = 300,
        poll_interval: float = 5,
    ) -> Router:
        """Wait for a router to reach an active state."""

        self._validate_wait_options(timeout, poll_interval)
        deadline = self._clock() + timeout
        while True:
            router = self._get_with_context(router_id)
            status = (router.status or "").lower()
            if status in {"ok", "available", "active"}:
                return router
            if status in {"failed", "error"}:
                raise MtnCloudError(
                    f"Router {router_id} provisioning failed: {status}",
                    response={"router_id": router_id, "status": status},
                )
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError(
                    f"Router {router_id} did not become ready",
                    timeout=timeout,
                    response={"router_id": router_id, "status": status},
                )
            self._sleeper(min(poll_interval, remaining))

    def wait_until_deleted(
        self,
        router_id: int,
        *,
        timeout: float = 300,
        poll_interval: float = 5,
    ) -> bool:
        """Wait until the router is no longer returned by the API."""

        self._validate_wait_options(timeout, poll_interval)
        deadline = self._clock() + timeout
        while True:
            try:
                self._get_with_context(router_id)
            except NotFoundError:
                return True
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError(
                    f"Router {router_id} was not deleted",
                    timeout=timeout,
                    response={"router_id": router_id},
                )
            self._sleeper(min(poll_interval, remaining))
