"""Resource registry: one entry per resource the CLI can list and describe."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mtn_cloud import MtnCloudClient


@dataclass(frozen=True)
class Column:
    header: str
    value: Callable[[Any], object]


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    service: Callable[[MtnCloudClient], Any]
    columns: tuple[Column, ...]
    exclude: frozenset[str] = frozenset()


def _network_type(network: Any) -> object:
    return network.type.name if network.type is not None else ""


REGISTRY: dict[str, ResourceSpec] = {
    "instances": ResourceSpec(
        name="instances",
        service=lambda client: client.instances,
        columns=(
            Column("ID", lambda m: m.id),
            Column("NAME", lambda m: m.name),
            Column("STATUS", lambda m: m.status),
            Column("IP", lambda m: m.ip_address),
        ),
        # Instance.config can carry customOptions such as passwords; never emit it.
        exclude=frozenset({"config"}),
    ),
    "networks": ResourceSpec(
        name="networks",
        service=lambda client: client.networks,
        columns=(
            Column("ID", lambda m: m.id),
            Column("NAME", lambda m: m.name),
            Column("CIDR", lambda m: m.cidr),
            Column("TYPE", _network_type),
        ),
        exclude=frozenset({"config"}),
    ),
    "routers": ResourceSpec(
        name="routers",
        service=lambda client: client.routers,
        columns=(
            Column("ID", lambda m: m.id),
            Column("NAME", lambda m: m.name),
            Column("STATUS", lambda m: m.status),
            Column("EXTERNAL IP", lambda m: m.external_ip),
        ),
    ),
}
