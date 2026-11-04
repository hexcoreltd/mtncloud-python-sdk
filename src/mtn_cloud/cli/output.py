"""Output helpers: format selection, JSON documents and stderr diagnostics."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from mtn_cloud.cli.errors import error_document

if TYPE_CHECKING:
    from mtn_cloud.cli.registry import Column

OutputFormat = Literal["json", "table"]


def stdout_is_terminal() -> bool:
    return sys.stdout.isatty()


def resolve_format(requested: str | None) -> OutputFormat:
    if requested == "json":
        return "json"
    if requested == "table":
        return "table"
    return "table" if stdout_is_terminal() else "json"


def emit_json(document: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_error(exc: BaseException, fmt: OutputFormat) -> None:
    """Write a diagnostic for ``exc`` to stderr. Never touches stdout."""
    document = error_document(exc)
    if fmt == "json":
        sys.stderr.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    else:
        err = document["error"]
        parts = [f"error: {err['type']}: {err['message']}"]
        if err["status_code"] is not None:
            parts.append(f"status={err['status_code']}")
        if err["method"] and err["path"]:
            parts.append(f"{err['method']} {err['path']}")
        if err["request_id"]:
            parts.append(f"request_id={err['request_id']}")
        sys.stderr.write(" ".join(parts) + "\n")
    sys.stderr.flush()


def dump_item(model: BaseModel, exclude: frozenset[str]) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude=set(exclude))


def list_document(resource: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "mtncloud.list/v1",
        "resource": resource,
        "count": len(items),
        "items": items,
    }


def describe_document(resource: str, item: dict[str, Any]) -> dict[str, Any]:
    return {"schema": "mtncloud.describe/v1", "resource": resource, "item": item}


def emit_table(columns: tuple[Column, ...], models: list[Any]) -> None:
    from rich.console import Console
    from rich.table import Table

    table = Table(*(column.header for column in columns))
    for model in models:
        table.add_row(
            *("" if (v := c.value(model)) is None else str(v) for c in columns),
        )
    Console(file=sys.stdout, highlight=False).print(table)
    sys.stdout.flush()
