"""Read-only backup CLI contracts; all HTTP requests use a mocked transport."""

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.cli import main
from mtn_cloud.transport import HttpResponse


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith("MTN_CLOUD_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MTN_CLOUD_TOKEN", "unit-test")
    monkeypatch.setenv("MTN_CLOUD_MAX_RETRIES", "0")


def run(transport: Mock, args: list[str]) -> int:
    def factory(settings: ClientSettings) -> MtnCloudClient:
        return MtnCloudClient(settings=settings, transport=transport)

    return main(args, client_factory=factory)


def response(body: Any, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, body, request_id="req-backup")


def test_backup_list_name_filter_and_pagination(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.side_effect = [
        response({"backups": [{"id": 1, "name": "nightly-a"}], "meta": {"total": 2}}),
        response({"backups": [{"id": 2, "name": "nightly-b"}], "meta": {"total": 2}}),
    ]
    assert run(transport, ["backups", "list", "--name", "nightly"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert (document["resource"], document["count"]) == ("backups", 2)
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": 0, "phrase": "nightly"},
        {"max": 100, "offset": 1, "phrase": "nightly"},
    ]
    assert all(call.args == ("GET", "/backups") for call in transport.request.call_args_list)


@pytest.mark.parametrize("target", ["42", "nightly"])
def test_backup_describe_by_id_or_exact_name(
    capsys: pytest.CaptureFixture[str], target: str
) -> None:
    transport = Mock()
    backup = {"id": 42, "name": "nightly", "enabled": False}
    transport.request.return_value = response(
        {"backup": backup} if target == "42" else {"backups": [backup]}
    )
    assert run(transport, ["backups", "describe", target]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["schema"] == "mtncloud.describe/v1"
    assert document["item"] == {"id": 42, "name": "nightly", "enabled": False}


@pytest.mark.parametrize(
    "command,key,path,resource",
    [
        (["backups", "jobs"], "jobs", "/backups/jobs", "backup-jobs"),
        (["backups", "results", "42"], "results", "/backups/42/results", "backup-results"),
    ],
)
def test_job_and_result_commands_follow_all_pages(
    capsys: pytest.CaptureFixture[str], command: list[str], key: str, path: str, resource: str
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        response({key: [{"id": 1}], "meta": {"total": 2}}),
        response({key: [{"id": 2}], "meta": {"total": 2}}),
    ]
    assert run(transport, command) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["schema"] == "mtncloud.list/v1"
    assert (document["resource"], document["count"]) == (resource, 2)
    assert [item["id"] for item in document["items"]] == [1, 2]
    if key == "results":
        assert document["backup_id"] == 42
        assert "backup_id" not in document["items"][0]
    assert all(call.args == ("GET", path) for call in transport.request.call_args_list)
    assert transport.request.call_args.kwargs["params"]["offset"] == 1


@pytest.mark.parametrize("command", ["list", "describe", "jobs", "results", "inventory"])
@pytest.mark.parametrize("fmt", ["json", "table"])
def test_sensitive_backup_fields_are_not_emitted(
    capsys: pytest.CaptureFixture[str], command: str, fmt: str
) -> None:
    item = {
        "id": 42,
        "name": "nightly",
        "status": "failed",
        "lastStatus": "failed",
        "config": {"secret": "unit-secret"},
        "errorMessage": "unit-secret",
        **{
            field: {"secret": "unit-secret"}
            for field in ["server", "instance", "container", "job", "storageProvider", "site"]
        },
    }
    args, key = {
        "list": (["backups", "list"], "backups"),
        "describe": (["backups", "describe", "42"], "backup"),
        "jobs": (["backups", "jobs"], "jobs"),
        "results": (["backups", "results", "42"], "results"),
        "inventory": (["inventory", "--only", "backups"], "backups"),
    }[command]
    transport = Mock()
    transport.request.return_value = response({key: item if command == "describe" else [item]})
    assert run(transport, [*args, "-o", fmt]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "unit-secret" not in captured.out
    if fmt == "json":
        document = json.loads(captured.out)
        if command == "inventory":
            selected = document["resources"]["backups"]["items"][0]
        else:
            selected = document["item"] if command == "describe" else document["items"][0]
        assert selected["id"] == 42
        assert not {
            "config",
            "error_message",
            "server",
            "instance",
            "container",
            "job",
            "storage_provider",
            "site",
        }.intersection(selected)


@pytest.mark.parametrize(
    "args",
    [
        ["backups", "list"],
        ["backups", "describe", "42"],
        ["backups", "jobs"],
        ["backups", "results", "42"],
        ["inventory", "--only", "backups"],
        ["inventory", "--only", "instances,backups"],
    ],
)
@pytest.mark.parametrize("flag", ["--group", "--zone"])
def test_unsupported_scope_fails_before_requests(
    capsys: pytest.CaptureFixture[str], args: list[str], flag: str
) -> None:
    transport = Mock()
    assert run(transport, [*args, flag, "production"]) == 2
    assert capsys.readouterr().out == ""
    transport.request.assert_not_called()


@pytest.mark.parametrize("target", ["0", "-1", "not-a-number"])
def test_results_require_positive_configuration_id(
    capsys: pytest.CaptureFixture[str], target: str
) -> None:
    transport = Mock()
    assert run(transport, ["backups", "results", target]) == 2
    assert capsys.readouterr().out == ""
    transport.request.assert_not_called()


@pytest.mark.parametrize(
    "args",
    [
        ["backups", "list"],
        ["backups", "describe", "42"],
        ["backups", "jobs"],
        ["backups", "results", "42"],
        ["inventory", "--only", "backups"],
    ],
)
def test_provider_errors_keep_exit_code_and_metadata_without_messages(
    capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    transport = Mock()
    transport.request.return_value = response({"message": "unit-secret"}, 403)
    assert run(transport, args) == 6
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unit-secret" not in captured.err
    error = json.loads(captured.err)["error"]
    assert error["type"] == "ForbiddenError"
    assert error["request_id"] == "req-backup"
    assert error["method"] == "GET"


@pytest.mark.parametrize("command", ["jobs", "results"])
def test_history_commands_do_not_emit_partial_results_on_later_error(
    capsys: pytest.CaptureFixture[str], command: str
) -> None:
    transport = Mock()
    key = "jobs" if command == "jobs" else "results"
    transport.request.side_effect = [
        response({key: [{"id": 1}], "meta": {"total": 2}}),
        response({"message": "unit-secret"}, 503),
    ]
    args = ["backups", command, "42"] if command == "results" else ["backups", command]
    assert run(transport, args) == 7
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unit-secret" not in captured.err


@pytest.mark.parametrize("command", ["execute", "execute-job", "delete", "restore"])
def test_mutating_backup_commands_are_not_registered(
    capsys: pytest.CaptureFixture[str], command: str
) -> None:
    transport = Mock()
    assert run(transport, ["backups", command, "42"]) == 2
    assert capsys.readouterr().out == ""
    transport.request.assert_not_called()


def test_backup_inventory_can_report_partial_failure(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()

    def request(method: str, path: str, **kwargs: Any) -> HttpResponse:
        if path == "/instances":
            return response({"instances": [{"id": 1}]})
        assert path == "/backups"
        return response({"message": "unit-secret"}, 403)

    transport.request.side_effect = request
    assert run(transport, ["inventory", "--only", "instances,backups"]) == 3
    captured = capsys.readouterr()
    assert "unit-secret" not in captured.out + captured.err
    assert json.loads(captured.out)["resources"]["backups"]["error"]["type"] == "ForbiddenError"


def test_configuration_lookup_requires_a_unique_exact_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = Mock()
    transport.request.return_value = response({"backups": [{"id": 1, "name": "nightly-old"}]})
    assert run(transport, ["backups", "describe", "nightly"]) == 4
    assert capsys.readouterr().out == ""
    transport.request.return_value = response(
        {"backups": [{"id": 1, "name": "nightly"}, {"id": 2, "name": "nightly"}]}
    )
    assert run(transport, ["backups", "describe", "nightly"]) == 5
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("args", [["backups", "jobs"], ["backups", "results", "42"]])
def test_history_output_format_validation_precedes_requests(
    capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    transport = Mock()
    assert run(transport, [*args, "-o", "yaml"]) == 2
    assert capsys.readouterr().out == ""
    transport.request.assert_not_called()


def test_backup_help_is_available_without_credentials(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MTN_CLOUD_TOKEN")
    transport = Mock()
    assert run(transport, ["backups", "--help"]) == 0
    text = capsys.readouterr().out
    assert all(command in text for command in ["list", "describe", "jobs", "results"])
    transport.request.assert_not_called()
