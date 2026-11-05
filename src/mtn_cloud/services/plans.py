"""Modern service for MTN Cloud service plans."""

from typing import Any, List

from mtn_cloud.models.plan import ServicePlan
from mtn_cloud.modern_exceptions import AmbiguousLookupError, MtnCloudError, NotFoundError
from mtn_cloud.services.base import Page, Service


class PlansService(Service[ServicePlan]):
    """Discover compute plans available to the tenant."""

    path = "/service-plans"
    item_key = "servicePlan"
    list_key = "servicePlans"
    model = ServicePlan

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
    ) -> Page[ServicePlan]:
        params: dict[str, Any] = {"max": limit, "offset": offset, "name": name}
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[ServicePlan]:
        return self.list_page(**kwargs).items

    def get(self, plan_id: int) -> ServicePlan:
        return self._get(plan_id)

    def get_by_name(self, name: str) -> ServicePlan:
        matches = [item for item in self.list(name=name, limit=100) if item.name == name]
        if not matches:
            raise NotFoundError(f"Service plan with name '{name}' not found")
        if len(matches) > 1:
            raise AmbiguousLookupError(f"Service plan name '{name}' is ambiguous")
        return matches[0]

    def list_for_provisioning(
        self,
        *,
        zone_id: int,
        layout_id: int,
        group_id: int,
        resource_pool_id: str | int,
    ) -> List[ServicePlan]:
        """List plans scoped to a tenant's actual provisioning context."""

        resource_pool = str(resource_pool_id)
        if resource_pool.isdigit():
            resource_pool = f"pool-{resource_pool}"
        body = self._core.request(
            "GET",
            "/instances/service-plans",
            params={
                "zoneId": zone_id,
                "layoutId": layout_id,
                "siteId": group_id,
                "resourcePoolId": resource_pool,
            },
        )
        if (
            not isinstance(body, dict)
            or body.get("success") is False
            or not isinstance(body.get("plans"), list)
        ):
            raise MtnCloudError(
                "Invalid provisioning service-plan response: expected a 'plans' list",
                method="GET",
                path="/instances/service-plans",
            )
        return [ServicePlan.model_validate(item) for item in body["plans"]]

    def get_for_provisioning(
        self,
        name: str,
        *,
        zone_id: int,
        layout_id: int,
        group_id: int,
        resource_pool_id: str | int,
    ) -> ServicePlan:
        matches = [
            plan
            for plan in self.list_for_provisioning(
                zone_id=zone_id,
                layout_id=layout_id,
                group_id=group_id,
                resource_pool_id=resource_pool_id,
            )
            if plan.name == name or plan.code == name or str(plan.id) == name
        ]
        if not matches:
            raise NotFoundError(f"Service plan '{name}' not found for this provisioning context")
        if len(matches) > 1:
            raise AmbiguousLookupError(f"Service plan '{name}' is ambiguous")
        return matches[0]
