"""Modern service for MTN Cloud provisioned applications."""

from typing import Any, List

from mtn_cloud.models.app import Application
from mtn_cloud.services.base import Page, Service


class ApplicationsService(Service[Application]):
    """Discover applications provisioned through MTN Cloud workflows."""

    path = "/apps"
    item_key = "app"
    list_key = "apps"
    model = Application

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
        status: str | None = None,
        group_id: int | None = None,
    ) -> Page[Application]:
        params = {
            "max": limit,
            "offset": offset,
            "name": name,
            "status": status,
            "siteId": group_id,
        }
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[Application]:
        return self.list_page(**kwargs).items

    def get(self, application_id: int) -> Application:
        return self._get(application_id)
