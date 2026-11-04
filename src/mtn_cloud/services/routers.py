"""Modern service for MTN Cloud routers and external networks."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, List

from mtn_cloud.core import CoreClient
from mtn_cloud.models.router import ExternalNetwork, Router, RouterCreate
from mtn_cloud.modern_exceptions import MtnCloudError, NotFoundError, TimeoutError
from mtn_cloud.services.base import Page, Service


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
        """Create an MTN router and optionally wait until it is ready."""

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
        router = self.get(router_id)
        return (
            self.wait_until_ready(router.id, timeout=timeout, poll_interval=poll_interval)
            if wait
            else router
        )

    def delete(self, router_id: int) -> bool:
        """Delete an MTN neutron router."""

        router = self.get(router_id)
        if router.type is None or router.type.code != "neutronRouter":
            raise ValueError(f"Router {router_id} is not an MTN neutronRouter")
        self._core.request("DELETE", f"{self.path}/{router_id}")
        return True

    def wait_until_ready(
        self,
        router_id: int,
        *,
        timeout: float = 300,
        poll_interval: float = 5,
    ) -> Router:
        """Wait for a router to reach an active state."""

        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("timeout and poll_interval must be positive")
        deadline = self._clock() + timeout
        while True:
            router = self.get(router_id)
            status = (router.status or "").lower()
            if status in {"ok", "available", "active"}:
                return router
            if status in {"failed", "error"}:
                raise MtnCloudError(f"Router {router_id} provisioning failed: {status}")
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError(
                    f"Router {router_id} did not become ready",
                    timeout=timeout,
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

        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("timeout and poll_interval must be positive")
        deadline = self._clock() + timeout
        while True:
            try:
                self.get(router_id)
            except NotFoundError:
                return True
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError(
                    f"Router {router_id} was not deleted",
                    timeout=timeout,
                )
            self._sleeper(min(poll_interval, remaining))
