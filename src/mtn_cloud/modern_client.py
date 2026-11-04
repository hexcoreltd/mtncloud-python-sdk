"""Modern MTN Cloud client foundation."""

import time
from typing import Any

from mtn_cloud.auth import CredentialProvider
from mtn_cloud.core import CoreClient
from mtn_cloud.models.user import User
from mtn_cloud.services.groups import GroupsService
from mtn_cloud.services.backups import BackupsService
from mtn_cloud.services.instance_types import InstanceTypesService
from mtn_cloud.services.instances import InstancesService
from mtn_cloud.services.networks import NetworksService
from mtn_cloud.services.plans import PlansService
from mtn_cloud.services.resource_pools import ResourcePoolsService
from mtn_cloud.services.routers import RoutersService
from mtn_cloud.services.security_groups import SecurityGroupsService
from mtn_cloud.services.volumes import VolumesService
from mtn_cloud.services.storage_buckets import StorageBucketsService
from mtn_cloud.services.apps import ApplicationsService
from mtn_cloud.services.zones import ZonesService
from mtn_cloud.settings import ClientSettings
from mtn_cloud.transport import Transport


class MtnCloudClient:
    """Synchronous MTN Cloud control-plane client.

    The initial API intentionally exposes only the verified foundation and
    current-user operation. Resource services will be added incrementally as
    their live contracts are confirmed.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        settings: ClientSettings | None = None,
        transport: Transport | None = None,
        credentials: CredentialProvider | None = None,
        sleeper: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        if settings is not None and token is not None:
            raise ValueError("Pass either settings or token, not both")
        self._settings = settings or ClientSettings(token=token)
        self._sleeper = sleeper or time.sleep
        self._clock = clock or time.monotonic
        self._core = CoreClient(
            self._settings,
            transport=transport,
            credentials=credentials,
            sleeper=self._sleeper,
        )
        self._zones: ZonesService | None = None
        self._groups: GroupsService | None = None
        self._instance_types: InstanceTypesService | None = None
        self._instances: InstancesService | None = None
        self._networks: NetworksService | None = None
        self._plans: PlansService | None = None
        self._resource_pools: ResourcePoolsService | None = None
        self._security_groups: SecurityGroupsService | None = None
        self._routers: RoutersService | None = None
        self._backups: BackupsService | None = None
        self._volumes: VolumesService | None = None
        self._storage_buckets: StorageBucketsService | None = None
        self._apps: ApplicationsService | None = None

    @property
    def settings(self) -> ClientSettings:
        return self._settings

    @property
    def zones(self) -> ZonesService:
        """Access deployment zones / regions."""

        if self._zones is None:
            self._zones = ZonesService(self._core)
        return self._zones

    @property
    def groups(self) -> GroupsService:
        """Access tenant groups / projects."""

        if self._groups is None:
            self._groups = GroupsService(self._core)
        return self._groups

    @property
    def instance_types(self) -> InstanceTypesService:
        """Access instance templates and their layouts."""

        if self._instance_types is None:
            self._instance_types = InstanceTypesService(self._core)
        return self._instance_types

    @property
    def instances(self) -> InstancesService:
        """Access compute instances."""

        if self._instances is None:
            self._instances = InstancesService(
                self._core,
                sleeper=self._sleeper,
                clock=self._clock,
                groups=self.groups,
                zones=self.zones,
                instance_types=self.instance_types,
                plans=self.plans,
                resource_pools=self.resource_pools,
                networks=self.networks,
            )
        return self._instances

    @property
    def networks(self) -> NetworksService:
        """Access tenant network discovery."""

        if self._networks is None:
            self._networks = NetworksService(self._core)
        return self._networks

    @property
    def plans(self) -> PlansService:
        """Access compute service plans."""

        if self._plans is None:
            self._plans = PlansService(self._core)
        return self._plans

    @property
    def resource_pools(self) -> ResourcePoolsService:
        """Access placement pools used during instance provisioning."""

        if self._resource_pools is None:
            self._resource_pools = ResourcePoolsService(self._core)
        return self._resource_pools

    @property
    def security_groups(self) -> SecurityGroupsService:
        """Access tenant security groups and firewall rules."""

        if self._security_groups is None:
            self._security_groups = SecurityGroupsService(self._core)
        return self._security_groups

    @property
    def routers(self) -> RoutersService:
        """Access tenant routers and external gateway options."""

        if self._routers is None:
            self._routers = RoutersService(
                self._core,
                sleeper=self._sleeper,
                clock=self._clock,
            )
        return self._routers

    @property
    def backups(self) -> BackupsService:
        """Access configured backups and backup execution results."""

        if self._backups is None:
            self._backups = BackupsService(self._core)
        return self._backups

    @property
    def volumes(self) -> VolumesService:
        """Access tenant block-storage volume discovery."""

        if self._volumes is None:
            self._volumes = VolumesService(self._core)
        return self._volumes

    @property
    def storage_buckets(self) -> StorageBucketsService:
        """Access S3-compatible storage-provider bucket configurations."""

        if self._storage_buckets is None:
            self._storage_buckets = StorageBucketsService(self._core)
        return self._storage_buckets

    @property
    def apps(self) -> ApplicationsService:
        """Access provisioned applications and catalog deployments."""

        if self._apps is None:
            self._apps = ApplicationsService(self._core)
        return self._apps

    def whoami(self) -> User:
        """Return the authenticated control-plane user."""

        body: Any = self._core.request("GET", "/whoami")
        payload = body.get("user", body) if isinstance(body, dict) else body
        return User.model_validate(payload)

    def ping(self) -> bool:
        """Return whether authentication and API connectivity are working."""

        self.whoami()
        return True

    def close(self) -> None:
        self._core.close()

    def __enter__(self) -> "MtnCloudClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
