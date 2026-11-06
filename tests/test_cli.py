from __future__ import annotations

import errno
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from rich.text import Text

from mtn_cloud import ClientSettings, MtnCloudClient, __version__
from mtn_cloud.cli import main, output
from mtn_cloud.cli.errors import (
    AmbiguousNameError,
    MissingCredentialsError,
    error_document,
    exit_code_for,
)
from mtn_cloud.modern_exceptions import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    LookupNotFoundError,
    MtnCloudError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TransportError,
    ValidationError,
)
from mtn_cloud.modern_exceptions import TimeoutError as ModernTimeoutError
from mtn_cloud.transport import HttpResponse

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith("MTN_CLOUD_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def _factory(settings: ClientSettings) -> MtnCloudClient:
    return MtnCloudClient(settings=settings, transport=Mock())


def _now() -> datetime:
    return datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)


def _run(argv: list[str]) -> int:
    return main(argv, client_factory=_factory, now=_now)


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (AuthenticationError("x"), 6),
        (ForbiddenError("x"), 6),
        (NotFoundError("x"), 4),
        (LookupNotFoundError("x"), 4),
        (AmbiguousNameError("x"), 5),
        (RateLimitError("x"), 7),
        (ServerError("x"), 7),
        (TransportError("x"), 7),
        (ConflictError("x"), 7),
        (ValidationError("x"), 7),
        (MtnCloudError("x"), 7),
        (ModernTimeoutError("x", timeout=1), 7),
        (MissingCredentialsError(), 6),
        (ValueError("x"), 1),
        (RuntimeError("x"), 1),
        (KeyboardInterrupt(), 130),
    ],
)
def test_exit_code_mapping(exc: BaseException, code: int) -> None:
    assert exit_code_for(exc) == code


def test_error_document_shape() -> None:
    exc = ForbiddenError(
        "denied", status_code=403, request_id="req-1", method="GET", path="/instances"
    )
    assert error_document(exc) == {
        "schema": "mtncloud.error/v1",
        "error": {
            "type": "ForbiddenError",
            "message": "denied",
            "status_code": 403,
            "request_id": "req-1",
            "method": "GET",
            "path": "/instances",
        },
    }


def test_error_document_for_non_sdk_error() -> None:
    doc: dict[str, Any] = error_document(RuntimeError("boom"))
    assert doc["error"] == {
        "type": "InternalError",
        "message": "internal error; rerun with --debug for details",
        "status_code": None,
        "request_id": None,
        "method": None,
        "path": None,
    }


def test_error_document_does_not_read_attributes_of_unknown_errors() -> None:
    exc = ImportError("x", path="/secret/path")
    exc.status_code = 500  # type: ignore[attr-defined]
    error = error_document(exc)["error"]
    assert error["path"] is None
    assert error["status_code"] is None


@pytest.mark.parametrize("exc", [AmbiguousNameError("two matches"), MissingCredentialsError()])
def test_error_document_for_cli_errors_keeps_message(exc: Exception) -> None:
    error = error_document(exc)["error"]
    assert error["type"] == type(exc).__name__
    assert error["message"] == str(exc)
    assert error["status_code"] is None


def test_version_prints_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["version", "-o", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "schema": "mtncloud.version/v1",
        "version": __version__,
    }


def test_version_table_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["version", "-o", "table"]) == 0
    assert __version__ in capsys.readouterr().out


def test_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["--help"]) == 0
    assert "mtncloud" in capsys.readouterr().out.lower()


def test_usage_error_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["instances", "--bogus"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err != ""


@pytest.mark.parametrize(
    ("args", "name"),
    [
        (["--timeout", "0", "version"], "timeout"),
        (["--base-url", "console.cloud.mtn.ng", "version"], "base_url"),
    ],
)
def test_invalid_settings_are_usage_errors(
    args: list[str], name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert name in captured.err.replace("-", "_")


def test_resolve_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output, "stdout_is_terminal", lambda: True)
    assert output.resolve_format(None) == "table"
    monkeypatch.setattr(output, "stdout_is_terminal", lambda: False)
    assert output.resolve_format(None) == "json"
    assert output.resolve_format("json") == "json"
    assert output.resolve_format("table") == "table"


def test_import_mtn_cloud_does_not_load_typer() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import mtn_cloud, sys; print('typer' in sys.modules, 'rich' in sys.modules)",
        ],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "False False\n"


def test_main_without_typer_exits_2_with_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "typer", None)
    monkeypatch.delitem(sys.modules, "mtn_cloud.cli.app", raising=False)
    assert main(["version"]) == 2
    assert 'pip install "mtncloud-python-sdk[cli]"' in capsys.readouterr().err


def test_broken_pipe_exits_quietly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(document: Any) -> None:
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    monkeypatch.setattr(output, "emit_json", boom)
    monkeypatch.setattr("mtn_cloud.cli._silence_stdout", lambda: None)
    assert _run(["version", "-o", "json"]) == 0
    assert "Traceback" not in capsys.readouterr().err


def test_unexpected_error_exits_1_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(document: Any) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(output, "emit_json", boom)
    assert _run(["version", "-o", "json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "kaboom" not in captured.err
    assert "InternalError" in captured.err
    assert "Traceback" not in captured.err


def test_console_script_is_declared() -> None:
    text = (ROOT / "pyproject.toml").read_text()
    assert re.search(r'^mtncloud = "mtn_cloud\.cli:main"$', text, re.MULTILINE)


def _failing_emit(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(document: Any) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(output, "emit_json", boom)


def test_command_level_output_wins_for_error_format(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _failing_emit(monkeypatch)
    assert _run(["-o", "table", "version", "-o", "json"]) == 1
    assert json.loads(capsys.readouterr().err)["schema"] == "mtncloud.error/v1"


def test_debug_as_option_value_prints_no_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _failing_emit(monkeypatch)
    assert _run(["--base-url", "--debug", "version"]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_debug_prints_traceback_on_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _failing_emit(monkeypatch)
    assert _run(["--debug", "version", "-o", "json"]) == 1
    assert "Traceback" in capsys.readouterr().err


def test_bare_invocation_prints_help_and_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run([]) == 0
    captured = capsys.readouterr()
    assert "Usage" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("argv", [["--help"], [], ["version", "-o", "json"], ["version"]])
def test_real_closed_pipe_exits_0(argv: list[str], tmp_path: Path) -> None:
    script = (
        "import sys, time\\n"
        "from mtn_cloud.cli import main\\n"
        "time.sleep(1)\\n"
        f"sys.exit(main({argv!r}))\\n"
    ).replace("\\n", "\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("MTN_CLOUD_")}
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=env,
    )
    assert proc.stdout is not None
    proc.stdout.close()
    assert proc.stderr is not None
    stderr = proc.stderr.read().decode()
    assert proc.wait(timeout=30) == 0
    assert "Traceback" not in stderr


# --- list and describe -------------------------------------------------------------------

PATHS = {
    "instances": ("/instances", "instances", "instance"),
    "networks": ("/networks", "networks", "network"),
    "routers": ("/networks/routers", "networkRouters", "networkRouter"),
}


def _resp(body: Any, status: int = 200) -> HttpResponse:
    return HttpResponse(status_code=status, headers={}, body=body)


def _run_with(
    transport: Mock, argv: list[str], monkeypatch: pytest.MonkeyPatch | None = None
) -> int:
    def factory(settings: ClientSettings) -> MtnCloudClient:
        return MtnCloudClient(settings=settings, transport=transport)

    return main(argv, client_factory=factory, now=_now)


@pytest.fixture
def token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MTN_CLOUD_TOKEN", "tok-test")


def _stderr_error(capsys: pytest.CaptureFixture[str]) -> tuple[str, dict[str, Any]]:
    captured = capsys.readouterr()
    return captured.out, json.loads(captured.err)


@pytest.mark.usefixtures("token")
def test_instances_list_json_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = _resp(
        {
            "instances": [
                {"id": 1, "name": "a", "status": "running", "ipAddress": "10.0.0.1"},
                {"id": 2, "name": "b", "status": "stopped"},
            ],
            "meta": {"offset": 0, "max": 100, "total": 2},
        }
    )
    assert _run_with(transport, ["instances", "list", "-o", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["schema"] == "mtncloud.list/v1"
    assert doc["resource"] == "instances"
    assert doc["count"] == 2
    assert [item["id"] for item in doc["items"]] == [1, 2]
    assert doc["items"][0]["ip_address"] == "10.0.0.1"


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize("resource", ["instances", "networks", "routers"])
def test_list_uses_scope_ids(resource: str) -> None:
    path, list_key, _ = PATHS[resource]
    transport = Mock()
    transport.request.return_value = _resp({list_key: []})
    argv = [resource, "list", "--group", "7", "--zone", "4", "-o", "json"]
    assert _run_with(transport, argv) == 0
    assert transport.request.call_count == 1
    call = transport.request.call_args
    assert call.args[1] == path
    assert call.kwargs["params"]["siteId"] == 7
    assert call.kwargs["params"]["zoneId"] == 4


@pytest.mark.usefixtures("token")
def test_list_name_filter_is_sent() -> None:
    transport = Mock()
    transport.request.return_value = _resp({"instances": []})
    assert _run_with(transport, ["instances", "list", "--name", "web", "-o", "json"]) == 0
    assert transport.request.call_args.kwargs["params"]["name"] == "web"


@pytest.mark.usefixtures("token")
def test_scope_names_resolve_to_ids() -> None:
    transport = Mock()
    transport.request.side_effect = [
        _resp({"groups": [{"id": 7, "name": "prod"}]}),
        _resp({"zones": [{"id": 4, "name": "lagos"}]}),
        _resp({"instances": []}),
    ]
    argv = ["instances", "list", "--group", "prod", "--zone", "lagos", "-o", "json"]
    assert _run_with(transport, argv) == 0
    params = transport.request.call_args_list[-1].kwargs["params"]
    assert params["siteId"] == 7
    assert params["zoneId"] == 4


@pytest.mark.usefixtures("token")
def test_ambiguous_group_exits_5(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = _resp(
        {"groups": [{"id": 7, "name": "prod"}, {"id": 8, "name": "prod"}]}
    )
    assert _run_with(transport, ["instances", "list", "--group", "prod", "-o", "json"]) == 5
    out, err = _stderr_error(capsys)
    assert out == ""
    assert err["error"]["type"] == "AmbiguousNameError"
    assert "ids [7, 8]" in err["error"]["message"]


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize("resource", ["instances", "networks", "routers"])
def test_describe_by_name_and_id(resource: str, capsys: pytest.CaptureFixture[str]) -> None:
    path, list_key, item_key = PATHS[resource]
    transport = Mock()
    transport.request.return_value = _resp({list_key: [{"id": 42, "name": "web"}]})
    assert _run_with(transport, [resource, "describe", "web", "-o", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["schema"] == "mtncloud.describe/v1"
    assert doc["resource"] == resource
    assert doc["item"]["id"] == 42
    assert transport.request.call_args.kwargs["params"]["name"] == "web"

    transport = Mock()
    transport.request.return_value = _resp({item_key: {"id": 42, "name": "web"}})
    assert _run_with(transport, [resource, "describe", "42", "-o", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["item"]["id"] == 42
    assert transport.request.call_count == 1
    assert transport.request.call_args.args[:2] == ("GET", f"{path}/42")


@pytest.mark.usefixtures("token")
def test_describe_numeric_argument_is_id(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = _resp({"message": "not found"}, 404)
    assert _run_with(transport, ["instances", "describe", "1234", "-o", "json"]) == 4
    assert transport.request.call_count == 1
    assert transport.request.call_args.args[:2] == ("GET", "/instances/1234")
    assert capsys.readouterr().out == ""


@pytest.mark.usefixtures("token")
def test_describe_not_found_exits_4(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = _resp({"instances": []})
    assert _run_with(transport, ["instances", "describe", "ghost", "-o", "json"]) == 4
    out, err = _stderr_error(capsys)
    assert out == ""
    assert err["error"]["type"] == "LookupNotFoundError"


@pytest.mark.usefixtures("token")
def test_describe_ambiguous_exits_5(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = _resp(
        {"instances": [{"id": 1, "name": "web"}, {"id": 2, "name": "web"}]}
    )
    assert _run_with(transport, ["instances", "describe", "web", "-o", "json"]) == 5
    out, err = _stderr_error(capsys)
    assert out == ""
    assert err["error"]["type"] == "AmbiguousNameError"
    assert "[1, 2]" in err["error"]["message"]


@pytest.mark.usefixtures("token")
def test_instance_config_is_excluded(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = _resp(
        {
            "instances": [
                {
                    "id": 1,
                    "name": "db",
                    "config": {"customOptions": {"dbPassword": "s3cret"}},
                }
            ]
        }
    )
    assert _run_with(transport, ["instances", "list", "-o", "json"]) == 0
    out = capsys.readouterr().out
    assert "config" not in json.loads(out)["items"][0]
    assert "s3cret" not in out


@pytest.mark.usefixtures("token")
def test_table_output_on_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(output, "stdout_is_terminal", lambda: True)
    transport = Mock()
    transport.request.return_value = _resp({"instances": [{"id": 1, "name": "a"}]})
    assert _run_with(transport, ["instances", "list"]) == 0
    out = capsys.readouterr().out
    for header in ("ID", "NAME", "STATUS"):
        assert header in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("failure", ["401", "raises"])
def test_token_never_printed(
    failure: str, debug: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MTN_CLOUD_TOKEN", "tok-SENTINEL-123")
    transport = Mock()
    if failure == "401":
        transport.request.return_value = _resp({"message": "unauthorized"}, 401)
    else:
        transport.request.side_effect = RuntimeError("boom")
    argv = (["--debug"] if debug else []) + ["instances", "list", "-o", "json"]
    assert _run_with(transport, argv) in (1, 6)
    captured = capsys.readouterr()
    assert "tok-SENTINEL-123" not in captured.out
    assert "tok-SENTINEL-123" not in captured.err


def test_missing_credentials_exit_6_without_request(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    assert _run_with(transport, ["instances", "list", "-o", "json"]) == 6
    transport.request.assert_not_called()
    out, err = _stderr_error(capsys)
    assert out == ""
    assert err["error"]["type"] == "MissingCredentialsError"


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize("command", ["list", "describe"])
def test_network_config_is_excluded(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    payload = {"id": 5, "name": "net", "config": {"secret": "s3cret"}}
    transport = Mock()
    if command == "list":
        transport.request.return_value = _resp({"networks": [payload]})
        argv = ["networks", "list", "-o", "json"]
    else:
        transport.request.return_value = _resp({"network": payload})
        argv = ["networks", "describe", "5", "-o", "json"]
    assert _run_with(transport, argv) == 0
    out = capsys.readouterr().out
    doc = json.loads(out)
    item = doc["items"][0] if command == "list" else doc["item"]
    assert "config" not in item
    assert "s3cret" not in out


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize(
    "argv",
    [
        ["instances", "describe", "web", "-o", "json"],
        ["instances", "list", "--group", "prod", "-o", "json"],
    ],
)
def test_malformed_payload_is_internal_error_not_ambiguous(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    transport = Mock()
    transport.request.return_value = _resp(
        {
            "instances": [{"id": "notint", "name": "web"}],
            "groups": [{"id": "notint", "name": "prod"}],
        }
    )
    assert _run_with(transport, argv) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.usefixtures("token")
def test_table_cells_are_not_parsed_as_markup(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = _resp({"instances": [{"id": 1, "name": "[/bold]oops"}]})
    assert _run_with(transport, ["instances", "list", "-o", "table"]) == 0
    assert "[/bold]oops" in capsys.readouterr().out


# --- inventory ---------------------------------------------------------------------------


def _inventory_transport(
    overrides: dict[str, HttpResponse] | None = None, default: HttpResponse | None = None
) -> Mock:
    bodies = {
        "/instances": _resp({"instances": [{"id": 1, "name": "a", "status": "running"}]}),
        "/networks": _resp({"networks": [{"id": 2, "name": "n", "config": {"s": 1}}]}),
        "/networks/routers": _resp({"networkRouters": [{"id": 3, "name": "r"}]}),
    }
    bodies.update(overrides or {})

    def request(method: str, path: str, **kwargs: Any) -> HttpResponse:
        return default if default is not None else bodies[path]

    transport = Mock()
    transport.request.side_effect = request
    return transport


@pytest.mark.usefixtures("token")
def test_inventory_document_snapshot(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_with(_inventory_transport(), ["inventory", "-o", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["schema"] == "mtncloud.inventory/v1"
    assert doc["generated_at"] == "2026-11-04T10:00:00Z"
    assert doc["sdk_version"] == __version__
    assert doc["base_url"] == "https://console.cloud.mtn.ng"
    assert doc["scope"] == {"group": None, "zone": None}
    assert list(doc["resources"]) == ["instances", "networks", "routers"]
    for section in doc["resources"].values():
        assert section["count"] == 1
        assert len(section["items"]) == 1
    assert "config" not in doc["resources"]["networks"]["items"][0]


@pytest.mark.usefixtures("token")
def test_inventory_partial_failure_exits_3(capsys: pytest.CaptureFixture[str]) -> None:
    transport = _inventory_transport({"/networks/routers": _resp({"message": "no"}, 403)})
    assert _run_with(transport, ["inventory", "-o", "json"]) == 3
    doc = json.loads(capsys.readouterr().out)
    routers = doc["resources"]["routers"]
    assert set(routers) == {"error"}
    assert routers["error"]["type"] == "ForbiddenError"
    assert routers["error"]["status_code"] == 403
    assert doc["resources"]["instances"]["count"] == 1
    assert doc["resources"]["networks"]["count"] == 1


def test_inventory_all_failed_uses_first_error_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MTN_CLOUD_TOKEN", "tok-test")
    monkeypatch.setenv("MTN_CLOUD_MAX_RETRIES", "0")
    transport = _inventory_transport(
        {
            "/instances": _resp({"message": "bad"}, 401),
            "/networks": _resp({"message": "down"}, 503),
            "/networks/routers": _resp({"message": "down"}, 503),
        }
    )
    assert _run_with(transport, ["inventory", "-o", "json"]) == 6
    out, err = _stderr_error(capsys)
    assert out == ""
    assert err["error"]["type"] == "AuthenticationError"


@pytest.mark.usefixtures("token")
def test_inventory_only_filters_sections(capsys: pytest.CaptureFixture[str]) -> None:
    transport = _inventory_transport()
    assert _run_with(transport, ["inventory", "--only", "networks", "-o", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert list(doc["resources"]) == ["networks"]
    assert transport.request.call_count == 1


@pytest.mark.usefixtures("token")
def test_inventory_unknown_only_is_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    transport = _inventory_transport()
    assert _run_with(transport, ["inventory", "--only", "unknown-resource", "-o", "json"]) == 2
    assert capsys.readouterr().out == ""
    transport.request.assert_not_called()


@pytest.mark.usefixtures("token")
def test_inventory_scope_is_recorded(capsys: pytest.CaptureFixture[str]) -> None:
    transport = _inventory_transport()
    assert _run_with(transport, ["inventory", "--group", "7", "-o", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["scope"] == {"group": "7", "zone": None}
    assert all(c.kwargs["params"]["siteId"] == 7 for c in transport.request.call_args_list)


@pytest.mark.usefixtures("token")
def test_inventory_unresolvable_scope_fails_before_sections(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = Mock()
    transport.request.return_value = _resp({"groups": []})
    assert _run_with(transport, ["inventory", "--group", "missing", "-o", "json"]) == 4
    assert capsys.readouterr().out == ""
    assert transport.request.call_count == 1


@pytest.mark.usefixtures("token")
def test_inventory_table_mode(capsys: pytest.CaptureFixture[str]) -> None:
    transport = _inventory_transport({"/networks/routers": _resp({"message": "no"}, 403)})
    assert _run_with(transport, ["inventory", "-o", "table"]) == 3
    captured = capsys.readouterr()
    assert "instances" in captured.out
    assert "ForbiddenError" in captured.err


@pytest.mark.usefixtures("token")
def test_inventory_internal_error_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    transport = _inventory_transport({"/networks": _resp({"networks": [{"id": "notint"}]})})
    assert _run_with(transport, ["inventory", "-o", "json"]) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize("argv", [["instances", "list", "-o", "json"], ["inventory", "-o", "json"]])
@pytest.mark.parametrize("debug", [False, True])
def test_malformed_payload_does_not_leak_payload(
    argv: list[str], debug: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    transport = Mock()
    transport.request.return_value = _resp(
        {
            "instances": [{"name": "web", "config": {"customOptions": {"dbPassword": "s3cret"}}}],
            "networks": [],
            "networkRouters": [],
        }
    )
    assert _run_with(transport, (["--debug"] if debug else []) + argv) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    if debug:
        assert "Traceback" in captured.err
        return
    assert "s3cret" not in captured.err
    assert "input_value" not in captured.err
    assert json.loads(captured.err)["error"]["type"] == "InternalError"


@pytest.mark.parametrize(
    "resource", ["instances", "networks", "routers", "volumes", "storage-buckets"]
)
def test_resource_without_subcommand_prints_help_and_exits_0(
    resource: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run([resource]) == 0
    captured = capsys.readouterr()
    assert "list" in captured.out
    assert "describe" in captured.out


@pytest.mark.usefixtures("token")
def test_inventory_and_version_without_extra_args_still_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(["version"]) == 0
    capsys.readouterr()
    transport = _inventory_transport()
    assert _run_with(transport, ["inventory"]) == 0
    assert transport.request.call_count == 3


@pytest.mark.usefixtures("token")
def test_inventory_group_zero_is_sent() -> None:
    transport = _inventory_transport()
    assert _run_with(transport, ["inventory", "--group", "0", "-o", "json"]) == 0
    assert all(c.kwargs["params"]["siteId"] == 0 for c in transport.request.call_args_list)


@pytest.mark.usefixtures("token")
def test_list_group_zero_is_sent() -> None:
    transport = Mock()
    transport.request.return_value = _resp({"instances": []})
    assert _run_with(transport, ["instances", "list", "--group", "0", "-o", "json"]) == 0
    assert transport.request.call_args.kwargs["params"]["siteId"] == 0


def test_invalid_environment_setting_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MTN_CLOUD_TIMEOUT", "0")
    assert _run(["version"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "MTN_CLOUD_TIMEOUT" in captured.err
    assert "--timeout" not in captured.err


@pytest.mark.usefixtures("token")
def test_ctrl_c_exits_130_with_empty_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.side_effect = KeyboardInterrupt()
    assert _run_with(transport, ["instances", "list", "-o", "json"]) == 130
    assert capsys.readouterr().out == ""


# --- volumes -----------------------------------------------------------------------------


@pytest.mark.usefixtures("token")
def test_volumes_list_follows_pages_with_resource_specific_filters(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        _resp({"storageVolumes": [{"id": 1, "name": "data-a"}], "meta": {"total": 2}}),
        _resp({"storageVolumes": [{"id": 2, "name": "data-b"}], "meta": {"total": 2}}),
    ]
    assert _run_with(transport, ["volumes", "list", "--zone", "4", "--name", "data"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["resource"] == "volumes"
    assert document["count"] == 2
    assert [item["id"] for item in document["items"]] == [1, 2]
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": 0, "zoneId": 4, "phrase": "data"},
        {"max": 100, "offset": 1, "zoneId": 4, "phrase": "data"},
    ]
    assert all(
        call.args == ("GET", "/storage/volumes") for call in transport.request.call_args_list
    )


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize("target", ["42", "data"])
def test_volume_describe_by_id_and_exact_name(
    capsys: pytest.CaptureFixture[str], target: str
) -> None:
    volume = {"id": 42, "name": "data", "instanceId": None, "status": "available"}
    transport = Mock()
    transport.request.return_value = _resp(
        {"storageVolume": volume} if target == "42" else {"storageVolumes": [volume]}
    )
    assert _run_with(transport, ["volumes", "describe", target, "--zone", "4"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["schema"] == "mtncloud.describe/v1"
    assert document["item"]["attachment_state"] == "unattached"
    assert document["item"]["is_available"] is True
    if target == "42":
        assert transport.request.call_args.args == ("GET", "/storage/volumes/42")
    else:
        assert transport.request.call_args.kwargs["params"] == {
            "max": 100,
            "offset": 0,
            "zoneId": 4,
            "phrase": "data",
        }


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize(
    ("fields", "state", "available"),
    [
        ({"status": "ready"}, "unknown", False),
        ({"instanceId": None}, "unattached", False),
        ({"instanceId": None, "status": "ready"}, "unattached", True),
        ({"instanceId": 7, "status": "ready"}, "attached", False),
    ],
)
@pytest.mark.parametrize("command", ["list", "describe", "inventory"])
def test_volume_output_preserves_attachment_evidence_and_excludes_provider_metadata(
    capsys: pytest.CaptureFixture[str],
    fields: dict[str, Any],
    state: str,
    available: bool,
    command: str,
) -> None:
    volume = {
        "id": 42,
        "name": "data",
        "storageType": {"secret": "s3cret"},
        "datastore": {"secret": "s3cret"},
        "zone": {"secret": "s3cret"},
        **fields,
    }
    transport = Mock()
    transport.request.return_value = _resp(
        {"storageVolume": volume} if command == "describe" else {"storageVolumes": [volume]}
    )
    args = {
        "list": ["volumes", "list"],
        "describe": ["volumes", "describe", "42"],
        "inventory": ["inventory", "--only", "volumes"],
    }[command]
    assert _run_with(transport, args) == 0
    captured = capsys.readouterr()
    assert "s3cret" not in captured.out + captured.err
    document = json.loads(captured.out)
    if command == "inventory":
        assert list(document["resources"]) == ["volumes"]
        item = document["resources"]["volumes"]["items"][0]
    else:
        item = document["item"] if command == "describe" else document["items"][0]
    assert item["attachment_state"] == state
    assert item["is_available"] is available
    assert ("instance_id" in item) is ("instanceId" in fields)
    assert not {"storage_type", "datastore", "zone"}.intersection(item)


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize(
    "args",
    [
        ["volumes", "list"],
        ["volumes", "describe", "data"],
        ["volumes", "describe", "42"],
        ["inventory", "--only", "volumes"],
        ["inventory", "--only", "instances,volumes"],
    ],
)
def test_volume_group_scope_is_rejected_before_discovery(
    capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    transport = Mock()
    assert _run_with(transport, [*args, "--group", "production"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "group scope" in captured.err
    transport.request.assert_not_called()


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"storageVolumes": []}, 4),
        ({"storageVolumes": [{"id": 1, "name": "data"}, {"id": 2, "name": "data"}]}, 5),
    ],
)
def test_volume_lookup_exit_codes(
    capsys: pytest.CaptureFixture[str], body: dict[str, Any], code: int
) -> None:
    transport = Mock()
    transport.request.return_value = _resp(body)
    assert _run_with(transport, ["volumes", "describe", "data"]) == code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["schema"] == "mtncloud.error/v1"


@pytest.mark.usefixtures("token")
def test_inventory_can_mix_volumes_with_other_resources(capsys: pytest.CaptureFixture[str]) -> None:
    transport = _inventory_transport({"/storage/volumes": _resp({"storageVolumes": []})})
    assert _run_with(transport, ["inventory", "--only", "instances,volumes", "--zone", "4"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert list(document["resources"]) == ["instances", "volumes"]
    assert all(call.kwargs["params"]["zoneId"] == 4 for call in transport.request.call_args_list)


@pytest.mark.usefixtures("token")
def test_volumes_inventory_failure_preserves_partial_result(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = _inventory_transport({"/storage/volumes": _resp({"message": "denied"}, 403)})
    assert _run_with(transport, ["inventory", "--only", "instances,volumes"]) == 3
    document = json.loads(capsys.readouterr().out)
    assert document["resources"]["instances"]["count"] == 1
    assert document["resources"]["volumes"]["error"]["type"] == "ForbiddenError"


@pytest.mark.usefixtures("token")
def test_volume_table_exposes_unknown_attachment_state(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = _resp({"storageVolumes": [{"id": 42, "name": "data"}]})
    assert _run_with(transport, ["volumes", "list", "-o", "table"]) == 0
    text = capsys.readouterr().out
    assert "unknown" in text
    assert "ATTACHMENT" in text


@pytest.mark.usefixtures("token")
def test_volume_named_zone_is_resolved_without_group_lookup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        _resp({"zones": [{"id": 4, "name": "lagos-1"}]}),
        _resp({"storageVolumes": []}),
    ]
    assert _run_with(transport, ["volumes", "list", "--zone", "lagos-1"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0
    assert [call.args[1] for call in transport.request.call_args_list] == [
        "/zones",
        "/storage/volumes",
    ]
    assert transport.request.call_args.kwargs["params"] == {"max": 100, "offset": 0, "zoneId": 4}


@pytest.mark.parametrize("command", ["list", "describe"])
@pytest.mark.parametrize("force_color", [False, True], ids=["plain", "ansi"])
def test_volume_help_lists_supported_scope_only(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    force_color: bool,
) -> None:
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color" if force_color else "dumb")
    if force_color:
        monkeypatch.setenv("FORCE_COLOR", "1")
    assert _run(["volumes", command, "--help"]) == 0
    rendered = capsys.readouterr().out
    if force_color:
        assert "\x1b[" in rendered
    help_text = Text.from_ansi(rendered).plain
    assert "--zone" in help_text
    assert "--group" not in help_text


# --- storage bucket configurations --------------------------------------------------------


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize("command", ["list", "describe", "inventory"])
@pytest.mark.parametrize("fmt", ["json", "table"])
def test_bucket_cli_output_excludes_provider_credentials(
    capsys: pytest.CaptureFixture[str], command: str, fmt: str
) -> None:
    bucket = {
        "id": 42,
        "name": "backups",
        "providerType": "s3",
        "bucketName": "app-backups",
        "active": True,
        "readOnly": False,
        "config": {
            "accessKey": "unit-access",
            "secretKey": "unit-secret",
            "endpoint": "unit-endpoint",
        },
        "storageServer": {"id": 9, "name": "unit-provider-secret"},
        "unexpectedCredential": "unit-extra-secret",
    }
    transport = Mock()
    transport.request.return_value = _resp(
        {"storageBucket": bucket} if command == "describe" else {"storageBuckets": [bucket]}
    )
    args = {
        "list": ["storage-buckets", "list"],
        "describe": ["storage-buckets", "describe", "42"],
        "inventory": ["inventory", "--only", "storage-buckets"],
    }[command]
    assert _run_with(transport, [*args, "-o", fmt]) == 0
    captured = capsys.readouterr()
    for marker in (
        "unit-access",
        "unit-secret",
        "unit-endpoint",
        "unit-provider-secret",
        "unit-extra-secret",
    ):
        assert marker not in captured.out + captured.err
    assert captured.err == ""
    if fmt == "json":
        document = json.loads(captured.out)
        if command == "inventory":
            assert list(document["resources"]) == ["storage-buckets"]
            item = document["resources"]["storage-buckets"]["items"][0]
        else:
            item = document["item"] if command == "describe" else document["items"][0]
        assert item == {
            "id": 42,
            "name": "backups",
            "provider_type": "s3",
            "bucket_name": "app-backups",
            "active": True,
            "read_only": False,
        }


@pytest.mark.usefixtures("token")
def test_bucket_cli_name_filter_and_pagination(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.side_effect = [
        _resp({"storageBuckets": [{"id": 1, "name": "backups-a"}], "meta": {"total": 2}}),
        _resp({"storageBuckets": [{"id": 2, "name": "backups-b"}], "meta": {"total": 2}}),
    ]
    assert _run_with(transport, ["storage-buckets", "list", "--name", "backups"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 2
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": 0, "name": "backups"},
        {"max": 100, "offset": 1, "name": "backups"},
    ]
    assert all(
        call.args == ("GET", "/storage-buckets") for call in transport.request.call_args_list
    )


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize(
    ("items", "code"),
    [
        ([{"id": 1, "name": "backups"}], 0),
        ([{"id": 1, "name": "backups-old"}], 4),
        ([{"id": 1, "name": "backups"}, {"id": 2, "name": "backups"}], 5),
    ],
)
def test_bucket_cli_exact_name_lookup_exit_codes(
    capsys: pytest.CaptureFixture[str], items: list[dict[str, Any]], code: int
) -> None:
    transport = Mock()
    transport.request.return_value = _resp({"storageBuckets": items})
    assert _run_with(transport, ["storage-buckets", "describe", "backups"]) == code
    captured = capsys.readouterr()
    if code == 0:
        assert json.loads(captured.out)["item"]["name"] == "backups"
    else:
        assert captured.out == ""
        assert json.loads(captured.err)["schema"] == "mtncloud.error/v1"


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize("scope", ["--group", "--zone"])
@pytest.mark.parametrize(
    "args",
    [
        ["storage-buckets", "list"],
        ["storage-buckets", "describe", "42"],
        ["storage-buckets", "describe", "backups"],
        ["inventory", "--only", "storage-buckets"],
        ["inventory", "--only", "instances,storage-buckets"],
    ],
)
def test_bucket_cli_unsupported_scope_fails_before_any_api_call(
    capsys: pytest.CaptureFixture[str], scope: str, args: list[str]
) -> None:
    transport = Mock()
    assert _run_with(transport, [*args, scope, "production"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "scope" in captured.err
    transport.request.assert_not_called()


@pytest.mark.parametrize("command", ["list", "describe"])
def test_bucket_cli_help_does_not_offer_unsupported_scopes(
    capsys: pytest.CaptureFixture[str], command: str
) -> None:
    assert _run(["storage-buckets", command, "--help"]) == 0
    help_text = Text.from_ansi(capsys.readouterr().out).plain
    assert "--zone" not in help_text
    assert "--group" not in help_text


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize(
    ("status", "code", "error_type"),
    [
        (403, 6, "ForbiddenError"),
        (404, 4, "NotFoundError"),
        (409, 7, "ConflictError"),
        (503, 7, "ServerError"),
    ],
)
@pytest.mark.parametrize(
    "args",
    [
        ["storage-buckets", "list"],
        ["storage-buckets", "describe", "42"],
        ["inventory", "--only", "storage-buckets"],
    ],
)
def test_bucket_cli_sanitizes_provider_errors_preserving_exit_codes(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    code: int,
    error_type: str,
    args: list[str],
) -> None:
    monkeypatch.setenv("MTN_CLOUD_MAX_RETRIES", "0")
    transport = Mock()
    transport.request.return_value = HttpResponse(
        status,
        {},
        {"message": "unit-secret", "config": {"secretKey": "unit-secret"}},
        request_id="req-bucket",
    )
    assert _run_with(transport, args) == code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unit-secret" not in captured.err
    error = json.loads(captured.err)["error"]
    assert error["type"] == error_type
    assert error["status_code"] == status
    assert error["request_id"] == "req-bucket"
    assert error["method"] == "GET"


@pytest.mark.usefixtures("token")
def test_bucket_inventory_partial_failure_sanitizes_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = _inventory_transport({"/storage-buckets": _resp({"message": "unit-secret"}, 403)})
    assert _run_with(transport, ["inventory", "--only", "instances,storage-buckets"]) == 3
    captured = capsys.readouterr()
    assert "unit-secret" not in captured.out + captured.err
    document = json.loads(captured.out)
    assert document["resources"]["instances"]["count"] == 1
    assert document["resources"]["storage-buckets"]["error"]["type"] == "ForbiddenError"


@pytest.mark.parametrize(
    "original",
    [
        ForbiddenError(
            "unit-secret", status_code=403, response={"secret": "unit-secret"}, request_id="req-1"
        ),
        ModernTimeoutError("unit-secret", timeout=5, method="GET", path="/storage-buckets/7"),
    ],
)
def test_bucket_error_redaction_preserves_error_class_without_mutating_original(
    original: MtnCloudError,
) -> None:
    from mtn_cloud.cli.registry import REGISTRY

    sanitized = REGISTRY["storage-buckets"].error_for_output(original)
    assert type(sanitized) is type(original)
    assert sanitized is not original
    assert "unit-secret" not in str(sanitized) + repr(sanitized)
    assert sanitized.response is None
    assert sanitized.status_code == original.status_code
    assert sanitized.request_id == original.request_id
    assert original.message == "unit-secret"
    if isinstance(original, ModernTimeoutError):
        assert sanitized.timeout == original.timeout


@pytest.mark.usefixtures("token")
@pytest.mark.parametrize("command", ["list", "describe", "inventory"])
def test_bucket_cli_malformed_payload_does_not_leak_provider_config(
    capsys: pytest.CaptureFixture[str], command: str
) -> None:
    invalid = {"name": "backups", "config": {"secretKey": "unit-secret"}}
    transport = Mock()
    transport.request.return_value = _resp(
        {"storageBucket": invalid} if command == "describe" else {"storageBuckets": [invalid]}
    )
    args = {
        "list": ["storage-buckets", "list"],
        "describe": ["storage-buckets", "describe", "42"],
        "inventory": ["inventory", "--only", "storage-buckets"],
    }[command]
    assert _run_with(transport, args) == (7 if command == "describe" else 1)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unit-secret" not in captured.err


@pytest.mark.usefixtures("token")
def test_bucket_table_errors_are_sanitized(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = HttpResponse(
        403, {}, {"message": "unit-secret"}, request_id="req-bucket"
    )
    assert _run_with(transport, ["storage-buckets", "list", "-o", "table"]) == 6
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unit-secret" not in captured.err
    assert "ForbiddenError" in captured.err and "req-bucket" in captured.err
