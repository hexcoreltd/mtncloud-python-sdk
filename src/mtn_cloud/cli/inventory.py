"""Inventory snapshot: one section per registered resource."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from mtn_cloud import MtnCloudClient, __version__
from mtn_cloud.cli.errors import EXIT_OK, EXIT_PARTIAL, error_document, exit_code_for
from mtn_cloud.cli.registry import ResourceSpec
from mtn_cloud.cli.scope import Scope, scope_filters
from mtn_cloud.modern_exceptions import MtnCloudError

INVENTORY_SCHEMA = "mtncloud.inventory/v1"

Section = tuple[ResourceSpec, "list[Any] | MtnCloudError"]


def collect_sections(
    client: MtnCloudClient, scope: Scope, specs: Sequence[ResourceSpec]
) -> list[Section]:
    """List every section, capturing SDK failures. Other errors propagate."""
    filters = scope_filters(scope)
    sections: list[Section] = []
    for spec in specs:
        try:
            sections.append((spec, list(spec.service(client).list_all(**filters))))
        except MtnCloudError as exc:
            sections.append((spec, spec.error_for_output(exc)))
    return sections


def exit_code_for_sections(sections: Sequence[Section]) -> int:
    """0 if all succeeded, 3 if some failed, else the first failure's code."""
    errors = [result for _, result in sections if isinstance(result, MtnCloudError)]
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
        if isinstance(result, MtnCloudError):
            resources[spec.name] = {"error": error_document(result)["error"]}
        else:
            items = [spec.dump_item(m) for m in result]
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
