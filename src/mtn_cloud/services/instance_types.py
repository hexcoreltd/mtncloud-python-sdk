"""Modern service for MTN Cloud instance types and layouts."""

from typing import Any

from mtn_cloud.models.instance_type import InstanceType
from mtn_cloud.modern_exceptions import NotFoundError
from mtn_cloud.services.base import Page, Service


class InstanceTypesService(Service[InstanceType]):
    """Discover operating-system and application templates."""

    path = "/instance-types"
    item_key = "instanceType"
    list_key = "instanceTypes"
    model = InstanceType

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
        code: str | None = None,
        category: str | None = None,
        featured: bool | None = None,
    ) -> Page[InstanceType]:
        params: dict[str, Any] = {
            "max": limit,
            "offset": offset,
            "name": name,
            "code": code,
            "category": category,
            "featured": featured,
        }
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> list[InstanceType]:
        return self.list_page(**kwargs).items

    def get(self, instance_type_id: int) -> InstanceType:
        return self._get(instance_type_id)

    def get_by_code(self, code: str) -> InstanceType:
        matches = [item for item in self.list(code=code, limit=100) if item.code == code]
        if not matches:
            raise NotFoundError(f"Instance type with code '{code}' not found")
        if len(matches) > 1:
            raise ValueError(f"Instance type code '{code}' is ambiguous")
        return matches[0]

    def get_by_name(self, name: str) -> InstanceType:
        matches = [item for item in self.list(name=name, limit=100) if item.name == name]
        if not matches:
            raise NotFoundError(f"Instance type with name '{name}' not found")
        if len(matches) > 1:
            raise ValueError(f"Instance type name '{name}' is ambiguous")
        return matches[0]
