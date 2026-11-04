"""Output helpers: format selection, JSON documents and stderr diagnostics."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any, Literal

from mtn_cloud.cli.errors import error_document

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
