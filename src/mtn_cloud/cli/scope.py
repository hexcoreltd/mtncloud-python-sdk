"""Resolve ``--group`` and ``--zone`` names or numeric IDs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mtn_cloud import MtnCloudClient
from mtn_cloud.cli.errors import AmbiguousNameError
from mtn_cloud.modern_exceptions import AmbiguousLookupError


@dataclass(frozen=True)
class Scope:
    group: str | None
    zone: str | None
    group_id: int | None
    zone_id: int | None


def is_id(value: str) -> bool:
    return value.isascii() and value.isdigit()


def _resolve(value: str | None, lookup: Callable[[str], Any]) -> int | None:
    if value is None:
        return None
    if is_id(value):
        return int(value)
    try:
        return int(lookup(value).id)
    except AmbiguousLookupError as exc:
        raise AmbiguousNameError(str(exc)) from exc


def resolve_scope(client: MtnCloudClient, *, group: str | None, zone: str | None) -> Scope:
    group_id = _resolve(group, client.groups.get_by_name)
    zone_id = _resolve(zone, client.zones.get_by_name)
    return Scope(group=group, zone=zone, group_id=group_id, zone_id=zone_id)


def scope_filters(scope: Scope) -> dict[str, int]:
    """API list filters for a scope; a ``0`` ID is a real value, only ``None`` is dropped."""
    filters = {"zone_id": scope.zone_id, "group_id": scope.group_id}
    return {k: v for k, v in filters.items() if v is not None}
