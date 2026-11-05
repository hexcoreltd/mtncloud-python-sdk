"""Modern service for instance placement resource pools."""

from typing import Any

from mtn_cloud.core import CoreClient
from mtn_cloud.models.resource_pool import ResourcePool
from mtn_cloud.modern_exceptions import AmbiguousLookupError, MtnCloudError, NotFoundError
from mtn_cloud.services.base import Page


class ResourcePoolsService:
    """Discover pools available for a zone and group combination."""

    path = "/options/zonePools"

    def __init__(self, core: CoreClient) -> None:
        self._core = core

    def list_page(
        self,
        *,
        zone_id: int,
        group_id: int,
        provision_type_code: str = "openstack",
    ) -> Page[ResourcePool]:
        params = {
            "cloudId": zone_id,
            "groupId": group_id,
            "provisionTypeCode": provision_type_code,
        }
        body = self._core.request("GET", self.path, params=params)
        if not isinstance(body, dict) or body.get("success") is False:
            raise MtnCloudError("Invalid resource-pool response", method="GET", path=self.path)

        raw_items = body.get("data")
        if not isinstance(raw_items, list):
            raise MtnCloudError(
                "Invalid resource-pool response: expected 'data' to be a list",
                method="GET",
                path=self.path,
            )

        pools = [
            ResourcePool.model_validate(item)
            for item in raw_items
            if isinstance(item, dict) and not item.get("isGroup") and "id" in item
        ]
        return Page(items=pools, total=len(pools), offset=0, limit=len(pools))

    def list(self, **kwargs: Any) -> list[ResourcePool]:
        return self.list_page(**kwargs).items

    def get_by_name(
        self,
        name: str,
        *,
        zone_id: int,
        group_id: int,
        provision_type_code: str = "openstack",
    ) -> ResourcePool:
        pools = self.list(
            zone_id=zone_id,
            group_id=group_id,
            provision_type_code=provision_type_code,
        )
        matches = [pool for pool in pools if pool.name == name or pool.code == name]
        if not matches:
            raise NotFoundError(f"Resource pool '{name}' not found")
        if len(matches) > 1:
            raise AmbiguousLookupError(f"Resource pool '{name}' is ambiguous")
        return matches[0]
