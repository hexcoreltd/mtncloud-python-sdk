"""Modern service for MTN Cloud compute instances."""

import time
from collections.abc import Callable, Mapping
from typing import Any, List, cast

from pydantic import ValidationError as ModelValidationError

from mtn_cloud.core import CoreClient
from mtn_cloud.models.cloud import Cloud
from mtn_cloud.models.group import Group
from mtn_cloud.models.instance import (
    Instance,
    InstanceCreate,
    InstanceNetwork,
    InstanceUpdate,
    InstanceVolume,
)
from mtn_cloud.models.instance_type import InstanceType
from mtn_cloud.models.plan import ServicePlan
from mtn_cloud.models.snapshot import Snapshot, SnapshotCreate, SnapshotSubmission
from mtn_cloud.modern_exceptions import (
    AmbiguousLookupError,
    LookupNotFoundError,
    MtnCloudError,
    TimeoutError,
)
from mtn_cloud.services.base import Page, Service
from mtn_cloud.services.groups import GroupsService
from mtn_cloud.services.instance_types import InstanceTypesService
from mtn_cloud.services.networks import NetworksService
from mtn_cloud.services.plans import PlansService
from mtn_cloud.services.resource_pools import ResourcePoolsService
from mtn_cloud.services.snapshots import (
    SnapshotsService,
    require_snapshot_success,
    validate_snapshot_id,
)
from mtn_cloud.services.zones import ZonesService


class InstancesService(Service[Instance]):
    """List, create, update, and delete compute instances."""

    path = "/instances"
    item_key = "instance"
    list_key = "instances"
    model = Instance

    def __init__(
        self,
        core: CoreClient,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        groups: GroupsService | None = None,
        zones: ZonesService | None = None,
        instance_types: InstanceTypesService | None = None,
        plans: PlansService | None = None,
        resource_pools: ResourcePoolsService | None = None,
        networks: NetworksService | None = None,
    ) -> None:
        super().__init__(core)
        self._sleeper = sleeper
        self._clock = clock
        self._groups = groups
        self._zones = zones
        self._instance_types = instance_types
        self._plans = plans
        self._resource_pools = resource_pools
        self._networks = networks

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
        status: str | None = None,
        zone_id: int | None = None,
        group_id: int | None = None,
    ) -> Page[Instance]:
        params: dict[str, Any] = {
            "max": limit,
            "offset": offset,
            "name": name,
            "status": status,
            "zoneId": zone_id,
            "siteId": group_id,
        }
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[Instance]:
        return self.list_page(**kwargs).items

    def get(self, instance_id: int) -> Instance:
        return self._get(instance_id)

    def get_by_name(
        self, name: str, *, zone_id: int | None = None, group_id: int | None = None
    ) -> Instance:
        """Return the uniquely named instance, optionally scoped by zone or group."""

        return self._get_by_name("Instance", name, zone_id=zone_id, group_id=group_id)

    def create(self, request: InstanceCreate) -> Instance:
        body = self._core.request("POST", self.path, json=request.to_api_payload())
        return self._parse_item(body)

    def update(self, instance_id: int, request: InstanceUpdate) -> Instance:
        body = self._core.request(
            "PUT", f"{self.path}/{instance_id}", json=request.to_api_payload()
        )
        return self._parse_item(body)

    def delete(
        self,
        instance_id: int,
        *,
        force: bool = False,
        preserve_volumes: bool = False,
    ) -> bool:
        params: dict[str, str] = {}
        if force:
            params["force"] = "on"
        if preserve_volumes:
            params["preserveVolumes"] = "on"
        self._core.request(
            "DELETE",
            f"{self.path}/{instance_id}",
            params=params or None,
        )
        return True

    def start(self, instance_id: int) -> Instance:
        return self._action(instance_id, "start")

    def stop(self, instance_id: int) -> Instance:
        return self._action(instance_id, "stop")

    def restart(self, instance_id: int) -> Instance:
        return self._action(instance_id, "restart")

    def suspend(self, instance_id: int) -> Instance:
        return self._action(instance_id, "suspend")

    def _action(self, instance_id: int, action: str) -> Instance:
        self._core.request("PUT", f"{self.path}/{instance_id}/{action}")
        return self.get(instance_id)

    def wait_for_status(
        self,
        instance_id: int,
        target_status: str,
        *,
        timeout: float = 300,
        poll_interval: float = 5,
        on_status: Callable[[Instance], None] | None = None,
    ) -> Instance:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if poll_interval < 0:
            raise ValueError("poll_interval cannot be negative")

        target = target_status.strip().lower()
        deadline = self._clock() + timeout
        while True:
            instance = self.get(instance_id)
            if on_status is not None:
                on_status(instance)
            current = instance.status.lower()
            if current == target:
                return instance
            if current == "failed":
                raise MtnCloudError(
                    f"Instance {instance_id} entered failed state: {instance.status_message}"
                )
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for instance {instance_id} to reach '{target}'",
                    timeout=timeout,
                )
            self._sleeper(min(poll_interval, remaining))

    def wait_until_running(
        self,
        instance_id: int,
        *,
        timeout: float = 300,
        poll_interval: float = 5,
        on_status: Callable[[Instance], None] | None = None,
    ) -> Instance:
        return self.wait_for_status(
            instance_id,
            "running",
            timeout=timeout,
            poll_interval=poll_interval,
            on_status=on_status,
        )

    def wait_until_stopped(
        self,
        instance_id: int,
        *,
        timeout: float = 300,
        poll_interval: float = 5,
        on_status: Callable[[Instance], None] | None = None,
    ) -> Instance:
        return self.wait_for_status(
            instance_id,
            "stopped",
            timeout=timeout,
            poll_interval=poll_interval,
            on_status=on_status,
        )

    def list_snapshots(self, instance_id: int) -> List[Snapshot]:
        """Read an instance's snapshot collection; upstream defines no paging."""

        validate_snapshot_id(instance_id, "instance_id")
        path = f"{self.path}/{instance_id}/snapshots"
        body = self._core.request("GET", path)
        if (
            not isinstance(body, dict)
            or body.get("success") is False
            or not isinstance(body.get("snapshots"), list)
        ):
            raise MtnCloudError("Invalid snapshot collection response", method="GET", path=path)
        if any(
            not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0
            for item in body["snapshots"]
        ):
            raise MtnCloudError("Invalid snapshot identifier", method="GET", path=path)
        snapshots = [Snapshot.model_validate(item) for item in body["snapshots"]]
        for snapshot in snapshots:
            parent = snapshot.instance
            if isinstance(parent, Mapping) and "id" in parent:
                if type(parent["id"]) is not int or parent["id"] != instance_id:
                    raise MtnCloudError(
                        "Snapshot references a different parent instance", method="GET", path=path
                    )
        return snapshots

    def get_snapshot(self, instance_id: int, snapshot_id: int) -> Snapshot:
        """Find one snapshot ID in the instance-scoped collection."""
        validate_snapshot_id(instance_id, "instance_id")
        validate_snapshot_id(snapshot_id, "snapshot_id")
        matches = [item for item in self.list_snapshots(instance_id) if item.id == snapshot_id]
        if not matches:
            raise LookupNotFoundError("Snapshot was not found in the instance collection")
        if len(matches) > 1:
            raise AmbiguousLookupError("Snapshot ID is repeated in the instance collection")
        return matches[0]

    def get_snapshot_by_name(self, instance_id: int, name: str) -> Snapshot:
        """Require one exact name in an instance's snapshot collection."""
        matches = [item for item in self.list_snapshots(instance_id) if item.name == name]
        if not matches:
            raise LookupNotFoundError("Snapshot name was not found in the instance collection")
        if len(matches) > 1:
            raise AmbiguousLookupError("Snapshot name is ambiguous in the instance collection")
        return matches[0]

    def create_snapshot(
        self,
        instance_id: int,
        request: SnapshotCreate,
    ) -> SnapshotSubmission:
        """Submit asynchronous creation and return process IDs, not a snapshot ID."""

        validate_snapshot_id(instance_id, "instance_id")
        path = f"{self.path}/{instance_id}/snapshot"
        body = self._core.request(
            "PUT",
            path,
            json=request.to_api_payload(),
        )
        require_snapshot_success(body, method="PUT", path=path)
        try:
            return SnapshotSubmission(instance_id=instance_id, process_ids=body.get("processIds"))
        except ModelValidationError as exc:
            raise MtnCloudError(
                "Invalid snapshot submission response; inspect the instance before resubmitting",
                method="PUT",
                path=path,
                response={"instance_id": instance_id},
            ) from exc

    def revert_snapshot(self, instance_id: int, snapshot_id: int) -> bool:
        """Check instance membership and submit a restore; True is acknowledgement."""

        self.get_snapshot(instance_id, snapshot_id)
        path = f"{self.path}/{instance_id}/revert-snapshot/{snapshot_id}"
        body = self._core.request("PUT", path)
        require_snapshot_success(body, method="PUT", path=path)
        return True

    def delete_snapshot(self, instance_id: int, snapshot_id: int) -> bool:
        """Check instance membership and request snapshot deletion."""

        self.get_snapshot(instance_id, snapshot_id)
        return SnapshotsService(self._core).delete(snapshot_id)

    def provision(
        self,
        name: str,
        *,
        type_code: str,
        group: str | int,
        plan: str | int,
        zone: str | int | None = None,
        resource_pool: str | int | None = None,
        layout: int | str | None = None,
        wait: bool = True,
        timeout: float = 1800,
        poll_interval: float = 10,
        dry_run: bool = False,
        description: str | None = None,
        labels: List[str] | None = None,
        tags: dict[str, str] | None = None,
        security_group: str = "default",
        create_user: bool = True,
        network_id: int | str | None = None,
        external_network_id: str | None = None,
        root_volume_size_gb: int | None = 10,
        progress_callback: Callable[[Instance], None] | None = None,
    ) -> Instance | dict[str, Any]:
        """Resolve provisioning inputs and create an instance."""

        services = (
            self._groups,
            self._zones,
            self._instance_types,
            self._plans,
            self._resource_pools,
            self._networks,
        )
        if any(service is None for service in services):
            raise RuntimeError("InstancesService provisioning dependencies are not configured")
        groups, zones, instance_types, plans, resource_pools, networks = cast(
            tuple[
                GroupsService,
                ZonesService,
                InstanceTypesService,
                PlansService,
                ResourcePoolsService,
                NetworksService,
            ],
            services,
        )

        group_model = groups.get(group) if isinstance(group, int) else groups.get_by_name(group)
        zone_model = self._resolve_zone(group_model, zone, zones)
        instance_type = instance_types.get_by_code(type_code)
        layout_id = self._resolve_layout(instance_type, layout)
        pool_code = self._resolve_pool(
            resource_pools,
            resource_pool,
            zone_id=zone_model.id,
            group_id=group_model.id,
        )
        plan_model = self._resolve_plan(
            plans,
            plan,
            zone_id=zone_model.id,
            layout_id=layout_id,
            group_id=group_model.id,
            resource_pool_id=pool_code,
        )
        plan_id = plan_model.id
        if root_volume_size_gb is not None and plan_model.storage_gb is not None:
            if root_volume_size_gb > plan_model.storage_gb:
                raise ValueError(
                    f"root_volume_size_gb={root_volume_size_gb} exceeds "
                    f"plan storage {plan_model.storage_gb:g} GB"
                )
        if network_id is not None:
            self._validate_network(
                networks,
                network_id,
                zone_id=zone_model.id,
                group_id=group_model.id,
                resource_pool_id=pool_code,
            )
        cloud_name = zone_model.name or str(zone_model.id)

        request = InstanceCreate(
            name=name,
            cloud=cloud_name,
            type=type_code,
            group_id=group_model.id,
            layout=layout_id,
            plan=plan_id,
            resource_pool_id=pool_code,
            description=description,
            labels=labels or [],
            tags=tags or {},
            security_group=security_group,
            os_external_network_id=external_network_id,
            create_user=create_user,
            network_interfaces=(
                [InstanceNetwork(network_id=self._network_reference(network_id))]
                if network_id is not None
                else []
            ),
            volumes=(
                [InstanceVolume(name="root", size=root_volume_size_gb)]
                if root_volume_size_gb is not None
                else []
            ),
        )
        resolved = {
            "name": name,
            "cloud": cloud_name,
            "group_id": group_model.id,
            "zone_id": zone_model.id,
            "type": type_code,
            "layout": layout_id,
            "plan": plan_id,
            "resource_pool_id": pool_code,
        }
        if external_network_id is not None:
            resolved["external_network_id"] = external_network_id
        if dry_run:
            return resolved

        instance = self.create(request)
        return (
            self.wait_until_running(
                instance.id,
                timeout=timeout,
                poll_interval=poll_interval,
                on_status=progress_callback,
            )
            if wait
            else instance
        )

    @staticmethod
    def _network_reference(network_id: int | str) -> str:
        value = str(network_id).strip()
        return value if value.startswith("network-") else f"network-{value}"

    @staticmethod
    def _resolve_layout(instance_type: InstanceType, layout: int | str | None) -> int:
        if isinstance(layout, int):
            return layout
        if isinstance(layout, str):
            if layout.isdigit():
                return int(layout)
            matches = [item for item in instance_type.layouts if item.name == layout]
            if len(matches) > 1:
                raise AmbiguousLookupError(f"Layout '{layout}' is ambiguous")
            if matches:
                layout_id: object = matches[0].id
                if type(layout_id) is int:
                    return layout_id
                raise ValueError(f"Layout '{layout}' has an invalid identifier")
            raise LookupNotFoundError(
                f"Layout '{layout}' not found for instance type '{instance_type.code}'"
            )
        default_layout_id: object = instance_type.default_layout_id
        if type(default_layout_id) is not int:
            raise ValueError(f"Instance type '{instance_type.code}' has no available layout")
        return default_layout_id

    @staticmethod
    def _resolve_plan(
        plans: PlansService,
        plan: str | int,
        *,
        zone_id: int,
        layout_id: int,
        group_id: int,
        resource_pool_id: str,
    ) -> ServicePlan:
        if isinstance(plan, int):
            return plans.get_for_provisioning(
                str(plan),
                zone_id=zone_id,
                layout_id=layout_id,
                group_id=group_id,
                resource_pool_id=resource_pool_id,
            )
        if plan.isdigit():
            return plans.get_for_provisioning(
                plan,
                zone_id=zone_id,
                layout_id=layout_id,
                group_id=group_id,
                resource_pool_id=resource_pool_id,
            )
        return plans.get_for_provisioning(
            plan,
            zone_id=zone_id,
            layout_id=layout_id,
            group_id=group_id,
            resource_pool_id=resource_pool_id,
        )

    @staticmethod
    def _validate_network(
        networks: NetworksService,
        network_id: int | str,
        *,
        zone_id: int,
        group_id: int,
        resource_pool_id: str,
    ) -> None:
        numeric_id = int(str(network_id).removeprefix("network-"))
        network = networks.get(numeric_id)
        if network.cloud_id not in (None, zone_id):
            raise ValueError(
                f"Network {numeric_id} belongs to zone {network.cloud_id}, not zone {zone_id}"
            )
        if network.group and network.group.id not in (None, group_id):
            raise ValueError(
                f"Network {numeric_id} belongs to group {network.group.id}, not group {group_id}"
            )
        expected_pool = int(resource_pool_id.removeprefix("pool-"))
        if network.zone_pool and network.zone_pool.id not in (None, expected_pool):
            raise ValueError(
                f"Network {numeric_id} belongs to resource pool {network.zone_pool.id}, "
                f"not {resource_pool_id}"
            )

    def wait_until_deleted(
        self,
        instance_id: int,
        *,
        timeout: float = 300,
        poll_interval: float = 5,
    ) -> bool:
        deadline = self._clock() + timeout
        while True:
            try:
                self.get(instance_id)
            except Exception as exc:
                if getattr(exc, "status_code", None) == 404:
                    return True
                raise
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for instance {instance_id} to be deleted",
                    timeout=timeout,
                )
            self._sleeper(min(poll_interval, remaining))

    @staticmethod
    def _resolve_pool(
        pools: ResourcePoolsService,
        resource_pool: str | int | None,
        *,
        zone_id: int,
        group_id: int,
    ) -> str:
        if isinstance(resource_pool, int) or (
            isinstance(resource_pool, str) and resource_pool.strip().isdigit()
        ):
            return f"pool-{resource_pool}"
        available = pools.list(zone_id=zone_id, group_id=group_id)
        if resource_pool is not None:
            return pools.get_by_name(
                resource_pool,
                zone_id=zone_id,
                group_id=group_id,
            ).code
        if len(available) != 1:
            if not available:
                raise ValueError("No resource pools are available for this group and zone")
            names = ", ".join(pool.name or pool.code for pool in available)
            raise AmbiguousLookupError(
                f"Multiple resource pools are available; choose one: {names}"
            )
        return available[0].code

    @staticmethod
    def _resolve_zone(group: Group, zone: str | int | None, zones: ZonesService) -> Any:
        embedded = [item for item in group.zones if isinstance(item, dict)]
        if zone is None and embedded:
            return Cloud.model_validate(embedded[0])
        if zone is not None:
            wanted = str(zone)
            embedded_matches = [
                item
                for item in embedded
                if str(item.get("id")) == wanted or item.get("name") == wanted
            ]
            if len(embedded_matches) == 1:
                return Cloud.model_validate(embedded_matches[0])
            if len(embedded_matches) > 1:
                raise AmbiguousLookupError(f"Zone '{zone}' is ambiguous for group '{group.name}'")
        if isinstance(zone, int) or (isinstance(zone, str) and zone.isdigit()):
            return zones.get(int(zone))
        if isinstance(zone, str):
            return zones.get_by_name(zone)
        if not group.cloud_ids:
            raise ValueError(f"Group '{group.name or group.id}' has no associated zones")
        return zones.get(group.cloud_ids[0])

    def _parse_item(self, body: Any) -> Instance:
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid instance response: expected an object")
        payload = body.get(self.item_key, body)
        if not isinstance(payload, dict):
            raise MtnCloudError("Invalid instance response: expected an instance object")
        return self.model.model_validate(payload)
