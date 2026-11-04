"""Typed service clients exposed by the modern MTN Cloud client."""

from mtn_cloud.services.groups import GroupsService
from mtn_cloud.services.instances import InstancesService
from mtn_cloud.services.networks import NetworksService
from mtn_cloud.services.instance_types import InstanceTypesService
from mtn_cloud.services.plans import PlansService
from mtn_cloud.services.resource_pools import ResourcePoolsService
from mtn_cloud.services.routers import RoutersService
from mtn_cloud.services.security_groups import SecurityGroupsService
from mtn_cloud.services.zones import ZonesService

__all__ = [
    "GroupsService",
    "BackupsService",
    "InstancesService",
    "NetworksService",
    "InstanceTypesService",
    "PlansService",
    "ResourcePoolsService",
    "RoutersService",
    "SecurityGroupsService",
    "ZonesService",
]
from mtn_cloud.services.backups import BackupsService
