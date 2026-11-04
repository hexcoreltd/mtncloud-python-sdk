"""Inventory snapshot: one section per registered resource."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from mtn_cloud import MtnCloudClient, __version__
from mtn_cloud.cli import output
from mtn_cloud.cli.errors import EXIT_OK, EXIT_PARTIAL, error_document, exit_code_for
from mtn_cloud.cli.registry import ResourceSpec
from mtn_cloud.cli.scope import Scope

INVENTORY_SCHEMA = "mtncloud.inventory/v1"

Section = tuple[ResourceSpec, "list[Any] | Exception"]


def collect_sections(
    client: MtnCloudClient, scope: Scope, specs: Sequence[ResourceSpec]
) -> list[Section]:
    """List every section, capturing per-section failures. Ctrl-C still propagates."""
    filters = {k: v for k, v in {"zone_id": scope.zone_id, "group_id": scope.group_id}.items() if v}
    sections: list[Section] = []
    for spec in specs:
        try:
            sections.append((spec, list(spec.service(client).list_all(**filters))))
        except Exception as exc:
            sections.append((spec, exc))
    return sections


def exit_code_for_sections(sections: Sequence[Section]) -> int:
    """0 if all succeeded, 3 if some failed, else the first failure's code."""
    errors = [result for _, result in sections if isinstance(result, Exception)]
    if not errors:
        return EXIT_OK
    if len(errors) < len(sections):
        return EXIT_PARTIAL
    return exit_code_for(errors[0])


def build_inventory(
    client: MtnCloudClient,
    scope: Scope,
    specs: Sequence[ResourceSpec],
    *,
    base_url: str,
    now: Callable[[], datetime],
    sections: Sequence[Section] | None = None,
) -> tuple[dict[str, Any], int]:
    """Return the ``mtncloud.inventory/v1`` document and its exit code."""
    collected = list(sections) if sections is not None else collect_sections(client, scope, specs)
    resources: dict[str, Any] = {}
    for spec, result in collected:
        if isinstance(result, Exception):
            resources[spec.name] = {"error": error_document(result)["error"]}
        else:
            items = [output.dump_item(m, spec.exclude) for m in result]
            resources[spec.name] = {"count": len(items), "items": items}
    document = {
        "schema": INVENTORY_SCHEMA,
        "generated_at": now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sdk_version": __version__,
        "base_url": base_url,
        "scope": {"group": scope.group, "zone": scope.zone},
        "resources": resources,
    }
    return document, exit_code_for_sections(collected)
