"""Modern service for MTN Cloud zones."""

from typing import Any

from mtn_cloud.models.cloud import Cloud
from mtn_cloud.services.base import Page, Service


class ZonesService(Service[Cloud]):
    """List and retrieve deployment zones."""

    path = "/zones"
    item_key = "zone"
    list_key = "zones"
    model = Cloud

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
        group_id: int | None = None,
        type_code: str | None = None,
    ) -> Page[Cloud]:
        params: dict[str, Any] = {"max": limit, "offset": offset}
        if name is not None:
            params["name"] = name
        if group_id is not None:
            params["groupId"] = group_id
        if type_code is not None:
            params["type"] = type_code
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> list[Cloud]:
        return self.list_page(**kwargs).items

    def get(self, zone_id: int) -> Cloud:
        return self._get(zone_id)

    def get_by_name(self, name: str) -> Cloud:
        return self._get_by_name("Zone", name)
