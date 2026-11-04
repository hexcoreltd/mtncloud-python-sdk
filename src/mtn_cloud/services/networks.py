"""Modern service for MTN Cloud network discovery."""

from typing import Any, List

from mtn_cloud.models.network import (
    Network,
    NetworkCreate,
    NetworkPool,
    NetworkPoolIp,
    NetworkTypeInfo,
    NetworkUpdate,
    Subnet,
)
from mtn_cloud.modern_exceptions import MtnCloudError
from mtn_cloud.services.base import Page, Service


class NetworksService(Service[Network]):
    """Discover tenant networks and their subnets."""

    path = "/networks"
    item_key = "network"
    list_key = "networks"
    model = Network

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
        zone_id: int | None = None,
        group_id: int | None = None,
    ) -> Page[Network]:
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

    def list(self, **kwargs: Any) -> List[Network]:
        return self.list_page(**kwargs).items

    def get(self, network_id: int) -> Network:
        return self._get(network_id)

    def create(self, request: NetworkCreate) -> Network:
        """Create a tenant network from a typed request payload."""

        body = self._core.request("POST", self.path, json=request.to_api_payload())
        return self._parse_item(body)

    def update(self, network_id: int, request: NetworkUpdate) -> Network:
        """Update mutable network configuration."""

        body = self._core.request(
            "PUT",
            f"{self.path}/{network_id}",
            json=request.to_api_payload(),
        )
        return self._parse_item(body)

    def delete(self, network_id: int) -> bool:
        """Delete a tenant network."""

        self._core.request("DELETE", f"{self.path}/{network_id}")
        return True

    def list_subnets(self, network_id: int) -> List[Subnet]:
        body = self._core.request("GET", f"{self.path}/{network_id}/subnets")
        if not isinstance(body, dict) or not isinstance(body.get("subnets"), list):
            raise MtnCloudError("Invalid subnet response: expected a 'subnets' list")
        subnets = [Subnet.model_validate(item) for item in body["subnets"]]
        if any(subnet.network_id not in (None, network_id) for subnet in subnets):
            raise MtnCloudError(
                f"Subnet discovery for network {network_id} returned a subnet with a different parent network"
            )
        return subnets

    def list_types(
        self,
        *,
        name: str | None = None,
        code: str | None = None,
        phrase: str | None = None,
        openstack_only: bool = False,
    ) -> List[NetworkTypeInfo]:
        """List network types, optionally restricted to OpenStack types."""

        params: dict[str, Any] = {"max": 500}
        if name is not None:
            params["name"] = name
        if code is not None:
            params["code"] = code
        if phrase is not None:
            params["phrase"] = phrase
        body = self._core.request("GET", "/network-types", params=params)
        if not isinstance(body, dict) or not isinstance(body.get("networkTypes"), list):
            raise MtnCloudError("Invalid network-type response: expected a 'networkTypes' list")
        types = [NetworkTypeInfo.model_validate(item) for item in body["networkTypes"]]
        return [item for item in types if not openstack_only or item.is_openstack]

    def get_type(self, network_type_id: int) -> NetworkTypeInfo:
        """Retrieve a network type by numeric ID."""

        body = self._core.request("GET", f"/network-types/{network_type_id}")
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid network-type response")
        return NetworkTypeInfo.model_validate(body.get("networkType", body))

    def list_pools(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        phrase: str | None = None,
    ) -> List[NetworkPool]:
        """List IP pools used for static network address management."""

        params: dict[str, Any] = {"max": limit, "offset": offset, "phrase": phrase}
        body = self._core.request(
            "GET",
            f"{self.path}/pools",
            params={key: value for key, value in params.items() if value is not None},
        )
        if not isinstance(body, dict) or not isinstance(body.get("networkPools"), list):
            raise MtnCloudError("Invalid network-pool response: expected a 'networkPools' list")
        return [NetworkPool.model_validate(item) for item in body["networkPools"]]

    def get_pool(self, pool_id: int) -> NetworkPool:
        """Retrieve an IP pool by numeric ID."""

        body = self._core.request("GET", f"{self.path}/pools/{pool_id}")
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid network-pool response")
        return NetworkPool.model_validate(body.get("networkPool", body))

    def list_pool_ips(
        self,
        pool_id: int,
        *,
        limit: int | None = None,
        phrase: str | None = None,
        ip_address: str | None = None,
        hostname: str | None = None,
    ) -> List[NetworkPoolIp]:
        """List addresses tracked within an IP pool."""

        params = {
            "max": limit,
            "phrase": phrase,
            "ipAddress": ip_address,
            "hostname": hostname,
        }
        body = self._core.request(
            "GET",
            f"{self.path}/pools/{pool_id}/ips",
            params={key: value for key, value in params.items() if value is not None},
        )
        if not isinstance(body, dict) or not isinstance(body.get("networkPoolIps"), list):
            raise MtnCloudError("Invalid network-pool IP response")
        return [NetworkPoolIp.model_validate(item) for item in body["networkPoolIps"]]

    @staticmethod
    def _parse_item(body: Any) -> Network:
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid network response")
        payload = body.get("network", body)
        if not isinstance(payload, dict):
            raise MtnCloudError("Invalid network response")
        return Network.model_validate(payload)
