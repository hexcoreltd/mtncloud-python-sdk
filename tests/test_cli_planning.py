"""CLI planning through the real resolver, with no live requests or mutations."""

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import requests

from mtn_cloud import MtnCloudClient
from mtn_cloud.cli import main, output
from mtn_cloud.services.instances import InstancesService
from mtn_cloud.transport import HttpResponse

SECRET = "private-provisioning-secret"
ARGS = [
    "plan",
    "--name",
    "web-01",
    "--type-code",
    "alma",
    "--group",
    "production",
    "--plan",
    "G1S1",
]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith("MTN_CLOUD_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MTN_CLOUD_TOKEN", "unit-test-token")
    monkeypatch.setenv("MTN_CLOUD_MAX_RETRIES", "0")


@pytest.fixture
def catalog() -> dict[str, Any]:
    group = {"id": 621, "name": "production", "zones": [{"id": 4, "name": "MTNNG_CLOUD_AZ_1"}]}
    return {
        "/groups": {"groups": [group]},
        "/groups/621": {"group": group},
        "/instance-types": {
            "instanceTypes": [
                {
                    "id": 10,
                    "code": "alma",
                    "account": {"password": SECRET},
                    "instanceTypeLayouts": [{"id": 20, "name": "AlmaLinux 10"}],
                }
            ]
        },
        "/options/zonePools": {"data": [{"id": 214, "value": "pool-214", "name": "production"}]},
        "/instances/service-plans": {
            "plans": [
                {
                    "id": 30,
                    "name": "small",
                    "code": "G1S1",
                    "maxStorage": 20 * 1024**3,
                    "config": {"password": SECRET},
                    "priceSets": [{"secret": SECRET}],
                }
            ]
        },
        "/networks/50": {
            "network": {
                "id": 50,
                "zone": {"id": 4},
                "group": {"id": 621},
                "zonePool": {"id": 214},
                "config": {"password": SECRET},
            }
        },
    }


@pytest.fixture
def transport(catalog: dict[str, Any]) -> Mock:
    def request(method: str, path: str, **kwargs: Any) -> HttpResponse:
        assert method == "GET", "planning must never mutate resources"
        assert kwargs["json"] is None
        return HttpResponse(200, {}, catalog[path], request_id="req-plan")

    return Mock(request=Mock(side_effect=request))


def run(transport: Mock, args: list[str] | None = None) -> int:
    return main(
        ARGS + ["-o", "json"] if args is None else args,
        client_factory=lambda settings: MtnCloudClient(settings=settings, transport=transport),
    )


def test_plan_resolves_real_services_and_emits_versioned_json(
    transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(transport) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and SECRET not in captured.out
    assert json.loads(captured.out) == {
        "schema": "mtncloud.plan/v1",
        "resource": "instances",
        "dry_run": True,
        "resolved": {
            "name": "web-01",
            "cloud": "MTNNG_CLOUD_AZ_1",
            "group_id": 621,
            "zone_id": 4,
            "type": "alma",
            "layout": 20,
            "plan": 30,
            "resource_pool_id": "pool-214",
        },
        "options": {
            "network_id": None,
            "external_network_id": None,
            "root_volume_size_gb": 10,
            "security_group": "default",
            "create_user": True,
        },
    }
    assert [call.args[1] for call in transport.request.call_args_list] == [
        "/groups",
        "/instance-types",
        "/options/zonePools",
        "/instances/service-plans",
    ]
    assert transport.request.call_args.kwargs["params"] == {
        "zoneId": 4,
        "layoutId": 20,
        "siteId": 621,
        "resourcePoolId": "pool-214",
    }
    transport.close.assert_called_once()


def test_explicit_id_selectors_and_network_options(
    transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    args = [
        "plan",
        "--name",
        "web-02",
        "--type-code",
        "alma",
        "--group",
        "621",
        "--plan",
        "30",
        "--zone",
        "4",
        "--layout",
        "20",
        "--resource-pool",
        "214",
        "--network-id",
        "50",
        "--external-network-id",
        "public-network",
        "--root-volume-size-gb",
        "15",
        "--security-group",
        "app-access",
        "--no-create-user",
        "-o",
        "json",
    ]
    assert run(transport, args) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["resolved"]["name"] == "web-02"
    assert document["resolved"]["layout"] == 20
    assert document["options"] == {
        "network_id": 50,
        "external_network_id": "public-network",
        "root_volume_size_gb": 15,
        "security_group": "app-access",
        "create_user": False,
    }
    paths = [call.args[1] for call in transport.request.call_args_list]
    assert paths == ["/groups/621", "/instance-types", "/instances/service-plans", "/networks/50"]


def test_named_layout_and_pool_are_resolved(
    transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(transport, ARGS + ["--layout", "AlmaLinux 10", "--resource-pool", "production"]) == 0
    assert json.loads(capsys.readouterr().out)["resolved"]["resource_pool_id"] == "pool-214"


def test_command_output_overrides_global_format(
    transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(transport, ["-o", "table", *ARGS, "-o", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "mtncloud.plan/v1"


def test_table_renders_plan_and_literal_markup(
    transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["[bold]web[/bold]" if value == "web-01" else value for value in ARGS]
    assert run(transport, args + ["-o", "table"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "[bold]web[/bold]" in captured.out
    assert "dry_run" in captured.out and "True" in captured.out and "pool-214" in captured.out
    assert SECRET not in captured.out


def test_default_format_honors_terminal_detection(
    transport: Mock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(output, "stdout_is_terminal", lambda: False)
    assert run(transport, ARGS) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


@pytest.mark.parametrize(
    "option,value",
    [
        ("--name", " "),
        ("--name", "x" * 256),
        ("--type-code", ""),
        ("--group", "0"),
        ("--group", "-1"),
        ("--plan", "0"),
        ("--zone", "-1"),
        ("--resource-pool", "0"),
        ("--layout", "0"),
        ("--network-id", "0"),
        ("--network-id", "not-an-id"),
        ("--root-volume-size-gb", "0"),
        ("--security-group", " "),
        ("--external-network-id", " "),
        ("--output", "yaml"),
    ],
)
def test_invalid_options_fail_before_client_creation(
    option: str, value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    args = list(ARGS)
    if option in args:
        args[args.index(option) + 1] = value
    else:
        args += [option, value]
    factory = Mock()
    assert main(args, client_factory=factory) == 2
    assert capsys.readouterr().out == ""
    factory.assert_not_called()


@pytest.mark.parametrize("args", [["plan"], [*ARGS, "--apply"], [*ARGS, "--token", "secret"]])
def test_missing_arguments_and_mutation_or_credential_flags_are_usage_errors(
    args: list[str],
) -> None:
    factory = Mock()
    assert main(args, client_factory=factory) == 2
    factory.assert_not_called()


def test_missing_credentials_fail_without_requests(
    transport: Mock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MTN_CLOUD_TOKEN")
    assert run(transport) == 6
    captured = capsys.readouterr()
    assert (
        captured.out == ""
        and json.loads(captured.err)["error"]["type"] == "MissingCredentialsError"
    )
    transport.request.assert_not_called()


@pytest.mark.parametrize("status,code", [(401, 6), (403, 6), (404, 4), (429, 7), (503, 7)])
def test_provider_failures_preserve_exit_code_and_metadata_without_payload(
    transport: Mock, capsys: pytest.CaptureFixture[str], status: int, code: int
) -> None:
    transport.request.side_effect = None
    transport.request.return_value = HttpResponse(
        status, {}, {"message": SECRET, "config": {"key": SECRET}}, request_id="req-failure"
    )
    assert run(transport) == code
    captured = capsys.readouterr()
    assert captured.out == "" and SECRET not in captured.err
    error = json.loads(captured.err)["error"]
    assert error["status_code"] == status and error["request_id"] == "req-failure"
    assert error["method"] == "GET" and error["path"] == "/groups"
    transport.close.assert_called_once()


@pytest.mark.parametrize("area", ["group", "type", "plan", "pool"])
def test_ambiguous_selections_fail_with_exit_five(
    area: str, catalog: dict[str, Any], transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    # A real ambiguity is two resources with one name, so duplicates get new IDs.
    if area == "group":
        groups = catalog["/groups"]["groups"]
        groups.append({**groups[0], "id": groups[0]["id"] + 1000})
    elif area == "type":
        types = catalog["/instance-types"]["instanceTypes"]
        types.append({**types[0], "id": types[0]["id"] + 1000})
    elif area == "plan":
        catalog["/instances/service-plans"]["plans"] *= 2
    else:
        catalog["/options/zonePools"]["data"].append(
            {"id": 215, "value": "pool-215", "name": SECRET}
        )
    assert run(transport) == 5
    captured = capsys.readouterr()
    assert captured.out == "" and SECRET not in captured.err
    assert json.loads(captured.err)["error"]["type"] == "AmbiguousNameError"


def test_missing_service_plan_is_not_found(
    catalog: dict[str, Any], transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog["/instances/service-plans"]["plans"] = []
    assert run(transport) == 4
    assert capsys.readouterr().out == ""


def test_duplicate_named_layout_is_ambiguous(
    catalog: dict[str, Any], transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    layouts = catalog["/instance-types"]["instanceTypes"][0]["instanceTypeLayouts"]
    layouts.append({"id": 21, "name": "AlmaLinux 10"})
    assert run(transport, ARGS + ["--layout", "AlmaLinux 10", "-o", "json"]) == 5
    assert capsys.readouterr().out == ""


def test_duplicate_named_pool_is_ambiguous(
    catalog: dict[str, Any], transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog["/options/zonePools"]["data"].append(
        {"id": 215, "value": "pool-215", "name": "production"}
    )
    assert run(transport, ARGS + ["--resource-pool", "production", "-o", "json"]) == 5
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("failure", ["storage", "network"])
def test_incompatible_inputs_fail_without_a_success_document(
    failure: str, catalog: dict[str, Any], transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    if failure == "storage":
        catalog["/instances/service-plans"]["plans"][0]["maxStorage"] = 5 * 1024**3
    else:
        catalog["/networks/50"]["network"]["zone"]["id"] = 999
    assert run(transport, ARGS + ["--network-id", "50", "-o", "json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Could not resolve" in captured.err
    transport.close.assert_called_once()


@pytest.mark.parametrize(
    "path,body",
    [
        ("/options/zonePools", None),
        ("/options/zonePools", {}),
        ("/options/zonePools", {"success": False, "data": []}),
        ("/instances/service-plans", {"success": False, "plans": [{"id": 30, "code": "G1S1"}]}),
    ],
)
def test_rejected_or_malformed_discovery_envelopes_do_not_produce_plans(
    path: str,
    body: Any,
    catalog: dict[str, Any],
    transport: Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog[path] = body
    assert run(transport) == 7
    assert capsys.readouterr().out == ""


def test_invalid_provider_model_data_is_an_internal_error_without_inputs(
    catalog: dict[str, Any], transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog["/groups"]["groups"][0]["id"] = SECRET
    assert run(transport) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and SECRET not in captured.err


@pytest.mark.parametrize(
    "failure", [requests.ReadTimeout(SECRET), requests.ConnectionError(SECRET)]
)
def test_connection_failures_are_sanitized_api_errors(
    failure: Exception, transport: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    transport.request.side_effect = failure
    assert run(transport) == 7
    captured = capsys.readouterr()
    assert captured.out == "" and SECRET not in captured.err
    error = json.loads(captured.err)["error"]
    assert error["type"] == "TransportError" and error["path"] == "/groups"
    transport.close.assert_called_once()


def test_projection_omits_unknown_result_fields_and_forces_dry_run(
    transport: Mock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    provision = Mock(
        return_value={
            "name": "web-01",
            "cloud": "MTNNG_CLOUD_AZ_1",
            "group_id": 621,
            "zone_id": 4,
            "type": "alma",
            "layout": 20,
            "plan": 30,
            "resource_pool_id": "pool-214",
            "config": {"secret": SECRET},
            "external_network_id": SECRET,
        }
    )
    monkeypatch.setattr(InstancesService, "provision", provision)
    assert run(transport) == 0
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert provision.call_args.kwargs["dry_run"] is True
    assert provision.call_args.kwargs["wait"] is False
    transport.request.assert_not_called()


@pytest.mark.parametrize("result", [None, {"config": {"secret": SECRET}}])
def test_invalid_dry_run_results_fail_without_leaking_inputs(
    result: Any,
    transport: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(InstancesService, "provision", Mock(return_value=result))
    assert run(transport) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and SECRET not in captured.err
