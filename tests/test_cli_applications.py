"""Application CLI tests with isolated credentials and mocked HTTP transport."""

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
    return HttpResponse(status, {}, body, request_id="req-app")


def test_app_list_follows_pages_with_group_and_name_filters(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        response({"apps": [{"id": 1, "name": "ledger-a"}], "meta": {"total": 2}}),
        response({"apps": [{"id": 2, "name": "ledger-b"}], "meta": {"total": 2}}),
    ]
    assert run(transport, ["apps", "list", "--group", "7", "--name", "ledger"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert (document["resource"], document["count"]) == ("apps", 2)
    assert [call.kwargs["params"] for call in transport.request.call_args_list] == [
        {"max": 100, "offset": 0, "name": "ledger", "siteId": 7},
        {"max": 100, "offset": 1, "name": "ledger", "siteId": 7},
    ]
    assert all(call.args == ("GET", "/apps") for call in transport.request.call_args_list)


@pytest.mark.parametrize("command", ["list", "describe", "inventory"])
@pytest.mark.parametrize("fmt", ["json", "table"])
def test_app_output_excludes_configuration_and_nested_metadata(
    capsys: pytest.CaptureFixture[str], command: str, fmt: str
) -> None:
    item = {
        "id": 42,
        "name": "ledger",
        "status": "running",
        "type": "database",
        "environment": "production",
        "description": "unit-secret",
        "config": {"password": "unit-secret"},
        "group": {"secret": "unit-secret"},
        "cloud": {"secret": "unit-secret"},
        "instances": [{"password": "unit-secret"}],
    }
    transport = Mock()
    transport.request.return_value = response(
        {"app": item} if command == "describe" else {"apps": [item]}
    )
    args = {
        "list": ["apps", "list"],
        "describe": ["apps", "describe", "42"],
        "inventory": ["inventory", "--only", "apps"],
    }[command]
    assert run(transport, [*args, "-o", fmt]) == 0
    captured = capsys.readouterr()
    assert "unit-secret" not in captured.out + captured.err
    if fmt == "json":
        document = json.loads(captured.out)
        if command == "inventory":
            selected = document["resources"]["apps"]["items"][0]
        else:
            selected = document["item"] if command == "describe" else document["items"][0]
        assert selected == {
            "id": 42,
            "name": "ledger",
            "status": "running",
            "app_type": "database",
            "environment": "production",
        }


@pytest.mark.parametrize(
    "args", [["apps", "list"], ["apps", "describe", "ledger"], ["inventory", "--only", "apps"]]
)
def test_named_group_is_resolved_for_application_commands(
    capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        response({"groups": [{"id": 7, "name": "production"}]}),
        response({"apps": [{"id": 42, "name": "ledger"}]}),
    ]
    assert run(transport, [*args, "--group", "production"]) == 0
    capsys.readouterr()
    assert transport.request.call_args_list[0].args == ("GET", "/groups")
    assert transport.request.call_args.kwargs["params"]["siteId"] == 7


@pytest.mark.parametrize(
    "args",
    [
        ["apps", "list"],
        ["apps", "describe", "42"],
        ["apps", "describe", "ledger"],
        ["inventory", "--only", "apps"],
        ["inventory", "--only", "instances,apps"],
    ],
)
def test_zone_scope_is_rejected_before_requests(
    capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    transport = Mock()
    assert run(transport, [*args, "--zone", "lagos"]) == 2
    assert capsys.readouterr().out == ""
    transport.request.assert_not_called()


@pytest.mark.parametrize(
    "args",
    [
        ["apps", "list"],
        ["apps", "describe", "42"],
        ["inventory", "--only", "apps"],
        ["apps", "list", "--group", "production"],
        ["inventory", "--only", "apps", "--group", "production"],
    ],
)
def test_provider_and_scope_errors_are_sanitized(
    capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    transport = Mock()
    transport.request.return_value = response({"message": "unit-secret"}, 403)
    assert run(transport, args) == 6
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unit-secret" not in captured.err
    error = json.loads(captured.err)["error"]
    assert (error["type"], error["request_id"]) == ("ForbiddenError", "req-app")


def test_app_lookup_handles_missing_and_ambiguous_names(capsys: pytest.CaptureFixture[str]) -> None:
    transport = Mock()
    transport.request.return_value = response({"apps": [{"id": 1, "name": "ledger-old"}]})
    assert run(transport, ["apps", "describe", "ledger"]) == 4
    assert capsys.readouterr().out == ""
    transport.request.return_value = response(
        {"apps": [{"id": 1, "name": "ledger"}, {"id": 2, "name": "ledger"}]}
    )
    assert run(transport, ["apps", "describe", "ledger"]) == 5
    assert capsys.readouterr().out == ""


def test_cli_does_not_emit_duplicate_inventory_on_pagination_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        response({"apps": [{"id": 1}], "meta": {"total": 2}}),
        response({"apps": [{"id": 1}], "meta": {"total": 2}}),
    ]
    assert run(transport, ["apps", "list"]) == 7
    assert capsys.readouterr().out == ""
    assert transport.request.call_count == 2


def test_inventory_can_mix_group_scoped_instances_and_applications(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = Mock()
    transport.request.side_effect = [
        response({"instances": [{"id": 1}]}),
        response({"apps": [{"id": 42}]}),
    ]
    assert run(transport, ["inventory", "--only", "instances,apps", "--group", "7"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert list(document["resources"]) == ["instances", "apps"]
    assert all(call.kwargs["params"]["siteId"] == 7 for call in transport.request.call_args_list)


def test_app_help_works_without_credentials_and_lists_supported_scope(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MTN_CLOUD_TOKEN")
    transport = Mock()
    assert run(transport, ["apps", "list", "--help"]) == 0
    text = capsys.readouterr().out
    assert "--group" in text and "--zone" not in text
    transport.request.assert_not_called()
