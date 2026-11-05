"""Composite action adapter; prepare runs with only the Python standard library."""

from __future__ import annotations

import io
import json
import math
import os
import sys
import tempfile
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from mtn_cloud import ClientSettings, MtnCloudClient
    from mtn_cloud.transport import HttpResponse, Transport

    ClientFactory = Callable[[ClientSettings], MtnCloudClient]

PREFIX = "MTNCLOUD_ACTION_"
PLAN_INPUTS = {
    "NAME": "name",
    "TYPE_CODE": "type-code",
    "SERVICE_PLAN": "plan",
    "RESOURCE_POOL": "resource-pool",
    "LAYOUT": "layout",
    "NETWORK_ID": "network-id",
    "ROOT_VOLUME_SIZE_GB": "root-volume-size-gb",
}
RESOURCE_NAMES = frozenset(
    {"instances", "networks", "routers", "volumes", "storage-buckets", "backups", "apps"}
)
INVENTORY_FIELDS = frozenset(
    {
        "id",
        "name",
        "status",
        "ip_address",
        "external_ip",
        "cidr",
        "code",
        "enabled",
        "active",
        "provider_type",
        "bucket_name",
        "attachment_state",
        "is_unattached",
        "is_available",
        "instance_id",
        "size",
        "size_gb",
        "app_type",
        "category",
        "environment",
        "date_created",
        "last_updated",
    }
)


class InputError(ValueError):
    """Invalid action input, with a diagnostic that contains no input values."""


class ReadOnlyTransport:
    """Enforce GET-only calls at the action's transport boundary."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    def request(self, method: str, path: str, **kwargs: Any) -> HttpResponse:
        if method != "GET":
            raise RuntimeError("The action permits GET requests only")
        return self.transport.request(method, path, **kwargs)

    def close(self) -> None:
        self.transport.close()


def value(name: str, default: str = "") -> str:
    return os.environ.get(PREFIX + name, default).strip()


def mask_token() -> str:
    token = os.environ.get(PREFIX + "TOKEN", "")
    if token:
        escaped = token.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::add-mask::{escaped}", flush=True)
    if not token or any(character.isspace() or ord(character) < 32 for character in token):
        raise InputError("A nonempty API token without whitespace is required.")
    return token


def configuration() -> dict[str, Any]:
    command = value("COMMAND", "inventory")
    if command not in {"inventory", "plan"}:
        raise InputError("command must be inventory or plan.")
    base_url = value("BASE_URL", "https://console.cloud.mtn.ng").rstrip("/")
    try:
        parsed = urlsplit(base_url)
        valid_url = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and not parsed.path
            and (parsed.port is None or 1 <= parsed.port <= 65535)
            and not any(character.isspace() or ord(character) < 32 for character in base_url)
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        raise InputError(
            "base-url must be an HTTPS origin without credentials, paths or query strings."
        )
    try:
        timeout = float(value("TIMEOUT", "30"))
    except ValueError:
        raise InputError(
            "timeout must be a finite number greater than zero and at most 300."
        ) from None
    if not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise InputError("timeout must be a finite number greater than zero and at most 300.")
    argv = [f"--base-url={base_url}", f"--timeout={timeout}", "--output=json", command]
    selections = {"GROUP": "group", "ZONE": "zone", "ONLY": "only", **PLAN_INPUTS}
    for key, option in selections.items():
        selection = value(key)
        if any(ord(character) < 32 for character in selection):
            raise InputError(f"{option} must not contain control characters.")
        if not selection:
            continue
        if command == "inventory" and key in PLAN_INPUTS:
            raise InputError("Plan inputs cannot be used with inventory.")
        if command == "plan" and key == "ONLY":
            raise InputError("only cannot be used with plan.")
        argv.append(f"--{option}={selection}")
    if command == "plan" and not all(
        value(key) for key in ("NAME", "TYPE_CODE", "GROUP", "SERVICE_PLAN")
    ):
        raise InputError("plan requires name, type-code, group and service-plan.")
    return {"command": command, "base_url": base_url, "timeout": timeout, "argv": argv}


def append_outputs(values: dict[str, str]) -> None:
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        for key, item in values.items():
            if "\n" in item or "\r" in item:
                raise InputError("Invalid runner output path.")
            stream.write(f"{key}={item}\n")


def write_private(path: Path, document: Any) -> None:
    with open(
        path, "x", encoding="utf-8", opener=lambda name, flags: os.open(name, flags, 0o600)
    ) as stream:
        json.dump(document, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def prepare() -> int:
    mask_token()
    if os.environ.get("RUNNER_OS") != "Linux":
        raise InputError("This action currently supports Linux runners only.")
    config = configuration()
    work_dir = Path(tempfile.mkdtemp(prefix="mtncloud-", dir=os.environ["RUNNER_TEMP"])).resolve()
    write_private(work_dir / "config.json", config)
    append_outputs({"work-dir": str(work_dir)})
    print("MTN Cloud action inputs validated.")
    return 0


def safe_error(error: Any) -> dict[str, Any]:
    fields = ("type", "status_code", "request_id", "method", "path")
    result = {field: error.get(field) for field in fields} if isinstance(error, dict) else {}
    result = {key: item for key, item in result.items() if item is None or type(item) in {str, int}}
    return {
        **result,
        "message": "MTN Cloud command failed; check inputs, API access and availability.",
    }


def scalar_fields(document: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in document.items()
        if item is None or type(item) in {str, int, float, bool}
    }


def project_result(command: str, document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != f"mtncloud.{command}/v1":
        raise ValueError("Invalid CLI result schema")
    if command == "plan":
        if document.get("dry_run") is not True or document.get("resource") != "instances":
            raise ValueError("Invalid plan mode")
        return {
            "schema": document["schema"],
            "resource": "instances",
            "dry_run": True,
            "resolved": scalar_fields(document["resolved"]),
            "options": scalar_fields(document["options"]),
        }
    resources = document["resources"]
    if not isinstance(resources, dict) or not resources.keys() <= RESOURCE_NAMES:
        raise ValueError("Invalid inventory resources")
    sections: dict[str, Any] = {}
    for name, section in resources.items():
        if "error" in section:
            sections[name] = {"error": safe_error(section["error"])}
        else:
            items = section["items"]
            if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                raise ValueError("Invalid inventory items")
            sections[name] = {
                "count": len(items),
                "items": [
                    scalar_fields(
                        {key: val for key, val in item.items() if key in INVENTORY_FIELDS}
                    )
                    for item in items
                ],
            }
    return {
        **{key: document.get(key) for key in ("schema", "generated_at", "sdk_version", "base_url")},
        "scope": scalar_fields(
            {key: document.get("scope", {}).get(key) for key in ("group", "zone")}
        ),
        "resources": sections,
    }


def redact(document: Any, token: str) -> Any:
    if isinstance(document, str):
        return document.replace(token, "[REDACTED]")
    if isinstance(document, list):
        return [redact(item, token) for item in document]
    if isinstance(document, dict):
        return {key: redact(item, token) for key, item in document.items()}
    return document


def execute(*, client_factory: ClientFactory | None = None) -> int:
    from mtn_cloud import ClientSettings, MtnCloudClient
    from mtn_cloud.cli import main as cli_main
    from mtn_cloud.transport import RequestsTransport

    token = mask_token()
    work_dir = Path(os.environ[PREFIX + "WORK_DIR"])
    config = json.loads((work_dir / "config.json").read_text(encoding="utf-8"))
    # The action supplies every setting explicitly and never reads a caller .env.
    for key in list(os.environ):
        if key.upper().startswith("MTN_CLOUD_"):
            del os.environ[key]
    os.environ["MTN_CLOUD_TOKEN"] = token
    settings = ClientSettings(
        _env_file=None,
        token=token,
        base_url=config["base_url"],
        timeout=config["timeout"],
        verify_ssl=True,
        max_retries=1,
        api_prefix="/api",
    )
    clients: list[MtnCloudClient] = []

    def factory(ignored: ClientSettings) -> MtnCloudClient:
        if client_factory is not None:
            client = client_factory(settings)
        else:
            client = MtnCloudClient(
                settings=settings, transport=ReadOnlyTransport(RequestsTransport(settings))
            )
        clients.append(client)
        return client

    captured_out, captured_err = io.StringIO(), io.StringIO()
    old_cwd = Path.cwd()
    try:
        os.chdir(work_dir)
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            code = cli_main(config["argv"], client_factory=factory)
    finally:
        os.chdir(old_cwd)
        for client in clients:
            client.close()
    if code not in {0, 1, 2, 3, 4, 5, 6, 7, 130}:
        code = 1
    result, error = None, None
    if code in {0, 3}:
        try:
            result = project_result(config["command"], json.loads(captured_out.getvalue()))
        except (ValueError, KeyError, TypeError, AttributeError):
            code = 1
            error = safe_error(None)
    else:
        try:
            error = safe_error(json.loads(captured_err.getvalue()).get("error"))
        except (ValueError, AttributeError):
            error = safe_error(None)
    document = redact(
        {
            "schema": "mtncloud.action/v1",
            "command": config["command"],
            "exit_code": code,
            "result": result,
            "error": error,
        },
        token,
    )
    result_path = work_dir / "result.json"
    write_private(result_path, document)
    append_outputs({"result-path": str(result_path), "exit-code": str(code)})
    summary = ["### MTN Cloud", "", f"Command: `{config['command']}`. Exit code: `{code}`.", ""]
    if result is not None and config["command"] == "inventory":
        summary.extend(["| Resource | Result |", "| --- | --- |"])
        for name, section in result["resources"].items():
            summary.append(f"| {name} | {'failed' if 'error' in section else section['count']} |")
    elif result is not None:
        summary.append("Instance placement resolved in dry-run mode.")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
        stream.write("\n".join(summary) + "\n")
    print(f"MTN Cloud {config['command']} finished (exit code {code}).")
    return code


def main() -> int:
    try:
        if sys.argv[1:] == ["prepare"]:
            return prepare()
        if sys.argv[1:] == ["run"]:
            return execute()
        raise InputError("Expected prepare or run stage.")
    except InputError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2
    except Exception:
        print(
            "::error::MTN Cloud action failed internally; no provider output was logged.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
