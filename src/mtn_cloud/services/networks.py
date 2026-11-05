"""Modern service for MTN Cloud network discovery and management."""

from ipaddress import ip_address, ip_network
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
from mtn_cloud.modern_exceptions import LookupNotFoundError, MtnCloudError
from mtn_cloud.services.base import Page, Service
from mtn_cloud.services.groups import GroupsService
from mtn_cloud.services.resource_pools import ResourcePoolsService
from mtn_cloud.services.zones import ZonesService


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

    def get_by_name(
        self, name: str, *, zone_id: int | None = None, group_id: int | None = None
    ) -> Network:
        """Return the uniquely named network, optionally scoped by zone or group."""

        return self._get_by_name("Network", name, zone_id=zone_id, group_id=group_id)

    def validate_create(self, request: NetworkCreate) -> None:
        """Validate network addressing and placement using read-only requests.

        Requires explicit OpenStack type and resource pool IDs. Local input
        checks run before discovery. Permission and transport errors propagate;
        successful discovery is a preflight check, not a reservation.
        """

        self._validate_create_inputs(request)
        group = GroupsService(self._core).get(request.group_id)
        if not group.active:
            raise ValueError(f"Group {group.id} is inactive")
        if request.cloud_id not in group.cloud_ids:
            raise ValueError(f"Zone {request.cloud_id} is not associated with group {group.id}")
        zone = ZonesService(self._core).get(request.cloud_id)
        if not zone.is_enabled:
            raise ValueError(f"Zone {zone.id} is disabled")
        # The local checks ensure these optional model fields are present.
        assert request.type_id is not None and request.resource_pool_id is not None
        network_type = self.get_type(request.type_id)
        if not network_type.is_openstack or not network_type.creatable:
            raise ValueError(f"Network type {network_type.id} is not a creatable OpenStack type")
        pools = ResourcePoolsService(self._core).list(zone_id=zone.id, group_id=group.id)
        if not any(pool.id == request.resource_pool_id for pool in pools):
            raise ValueError(
                f"Resource pool {request.resource_pool_id} is not available "
                f"for group {group.id} and zone {zone.id}"
            )

    @staticmethod
    def _validate_create_inputs(request: NetworkCreate) -> None:
        if not request.name.strip():
            raise ValueError("Network name must not be empty")
        for name in ("cloud_id", "group_id", "type_id", "resource_pool_id"):
            value = getattr(request, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be an explicit positive integer for validation")
        subnet = ip_network(request.cidr, strict=True) if request.cidr is not None else None
        if request.gateway is not None:
            gateway = ip_address(request.gateway)
            if subnet is not None:
                if gateway.version != subnet.version or gateway not in subnet:
                    raise ValueError("Gateway must belong to the requested CIDR")
                if subnet.version == 4 and subnet.prefixlen < 31:
                    if gateway in (subnet.network_address, subnet.broadcast_address):
                        raise ValueError("Gateway must be a usable host address")
        for name in ("dns_primary", "dns_secondary"):
            value = getattr(request, name)
            if value is not None:
                try:
                    ip_address(value)
                except ValueError as exc:
                    raise ValueError(f"{name} must be an IP address") from exc

    def create(self, request: NetworkCreate, *, validate: bool = False) -> Network:
        """Create a network, optionally validating inputs and placement first.

        Validation uses additional permission-scoped discovery endpoints.
        It never creates resources and can be called separately via
        ``validate_create``. The POST is submitted only after validation passes.
        """

        if validate:
            self.validate_create(request)
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
        """List and validate subnets belonging to a network."""

        body = self._core.request("GET", f"{self.path}/{network_id}/subnets")
        if not isinstance(body, dict) or not isinstance(body.get("subnets"), list):
            raise MtnCloudError("Invalid subnet response: expected a 'subnets' list")
        subnets = [Subnet.model_validate(item) for item in body["subnets"]]
        if any(subnet.network_id not in (None, network_id) for subnet in subnets):
            raise MtnCloudError(
                f"Subnet discovery for network {network_id} returned a subnet with a different parent network"
            )
        return subnets

    def get_subnet(self, network_id: int, subnet_id: int) -> Subnet:
        """Return a subnet by ID, ensuring it belongs to the given network.

        The current MTN Cloud contract exposes subnet discovery through the
        parent network collection. This helper intentionally reuses that
        verified read-only operation instead of assuming an undocumented
        standalone subnet endpoint.
        """

        for subnet in self.list_subnets(network_id):
            if subnet.id == subnet_id:
                return subnet
        raise LookupNotFoundError(f"Subnet {subnet_id} was not found in network {network_id}")

    def get_subnet_by_name(self, network_id: int, name: str) -> Subnet:
        """Return a uniquely named subnet within a network."""

        matches = [subnet for subnet in self.list_subnets(network_id) if subnet.name == name]
        if not matches:
            raise LookupNotFoundError(f"Subnet '{name}' was not found in network {network_id}")
        if len(matches) > 1:
            raise ValueError(f"Subnet name '{name}' is ambiguous in network {network_id}")
        return matches[0]

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

    def get_pool_ip(self, pool_id: int, ip_address: str) -> NetworkPoolIp:
        """Return one pool address by its exact IP address."""

        matches = [
            item
            for item in self.list_pool_ips(pool_id, ip_address=ip_address)
            if item.ip_address == ip_address
        ]
        if not matches:
            raise LookupNotFoundError(f"IP address '{ip_address}' was not found in pool {pool_id}")
        if len(matches) > 1:
            raise ValueError(f"IP address '{ip_address}' is ambiguous in pool {pool_id}")
        return matches[0]

    @staticmethod
    def _parse_item(body: Any) -> Network:
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid network response")
        payload = body.get("network", body)
        if not isinstance(payload, dict):
            raise MtnCloudError("Invalid network response")
        return Network.model_validate(payload)
