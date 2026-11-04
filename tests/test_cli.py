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
    assert doc["error"]["type"] == "RuntimeError"
    assert doc["error"]["message"] == "boom"
    assert doc["error"]["status_code"] is None


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
        [sys.executable, "-c", "import mtn_cloud, sys; print('typer' in sys.modules)"],
        capture_output=True,
        text=True,
    )
    assert result.stdout == "False\n"


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
    assert "kaboom" in captured.err
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
