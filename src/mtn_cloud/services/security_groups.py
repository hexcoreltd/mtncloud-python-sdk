"""Modern service for MTN Cloud security groups and rules."""

from typing import Any, List

from mtn_cloud.models.security_group import (
    SecurityGroup,
    SecurityGroupCreate,
    SecurityGroupRule,
    SecurityGroupRuleCreate,
    SecurityGroupRuleUpdate,
    SecurityGroupUpdate,
)
from mtn_cloud.modern_exceptions import MtnCloudError, NotFoundError
from mtn_cloud.services.base import Page, Service


class SecurityGroupsService(Service[SecurityGroup]):
    """Discover and manage tenant security groups."""

    path = "/security-groups"
    item_key = "securityGroup"
    list_key = "securityGroups"
    model = SecurityGroup

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
    ) -> Page[SecurityGroup]:
        params = {"max": limit, "offset": offset, "name": name}
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[SecurityGroup]:
        return self.list_page(**kwargs).items

    def get(self, security_group_id: int) -> SecurityGroup:
        return self._get(security_group_id)

    def get_by_name(self, name: str) -> SecurityGroup:
        matches = [group for group in self.list(name=name, limit=100) if group.name == name]
        if not matches:
            raise NotFoundError(f"Security group '{name}' not found")
        if len(matches) > 1:
            raise ValueError(f"Security group '{name}' is ambiguous")
        return matches[0]

    def create(self, request: SecurityGroupCreate) -> SecurityGroup:
        body = self._core.request("POST", self.path, json=request.to_api_payload())
        return self._parse_item(body)

    def update(self, security_group_id: int, request: SecurityGroupUpdate) -> SecurityGroup:
        body = self._core.request(
            "PUT",
            f"{self.path}/{security_group_id}",
            json=request.to_api_payload(),
        )
        return self._parse_item(body)

    def delete(self, security_group_id: int) -> bool:
        self._core.request("DELETE", f"{self.path}/{security_group_id}")
        return True

    def list_rules(self, security_group_id: int) -> List[SecurityGroupRule]:
        group = self.get(security_group_id)
        return group.rules

    def create_rule(
        self, security_group_id: int, request: SecurityGroupRuleCreate
    ) -> SecurityGroupRule:
        body = self._core.request(
            "POST",
            f"{self.path}/{security_group_id}/rules",
            json=request.to_api_payload(),
        )
        return self._parse_rule(body)

    def update_rule(
        self,
        security_group_id: int,
        rule_id: int,
        request: SecurityGroupRuleUpdate,
    ) -> SecurityGroupRule:
        body = self._core.request(
            "PUT",
            f"{self.path}/{security_group_id}/rules/{rule_id}",
            json=request.to_api_payload(),
        )
        return self._parse_rule(body)

    def delete_rule(self, security_group_id: int, rule_id: int) -> bool:
        self._core.request("DELETE", f"{self.path}/{security_group_id}/rules/{rule_id}")
        return True

    @staticmethod
    def _parse_item(body: Any) -> SecurityGroup:
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid security-group response")
        payload = body.get("securityGroup", body)
        if not isinstance(payload, dict):
            raise MtnCloudError("Invalid security-group response")
        return SecurityGroup.model_validate(payload)

    @staticmethod
    def _parse_rule(body: Any) -> SecurityGroupRule:
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid security-group rule response")
        payload = body.get("rule", body)
        if not isinstance(payload, dict):
            raise MtnCloudError("Invalid security-group rule response")
        return SecurityGroupRule.model_validate(payload)
