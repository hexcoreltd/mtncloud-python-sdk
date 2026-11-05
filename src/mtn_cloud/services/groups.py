"""Modern service for MTN Cloud groups/projects."""

from typing import Any

from mtn_cloud.models.group import Group
from mtn_cloud.services.base import Page, Service


class GroupsService(Service[Group]):
    """List and retrieve tenant groups/projects."""

    path = "/groups"
    item_key = "group"
    list_key = "groups"
    model = Group

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
    ) -> Page[Group]:
        params: dict[str, Any] = {"max": limit, "offset": offset}
        if name is not None:
            params["name"] = name
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> list[Group]:
        return self.list_page(**kwargs).items

    def get(self, group_id: int) -> Group:
        return self._get(group_id)

    def get_by_name(self, name: str) -> Group:
        return self._get_by_name("Group", name)
