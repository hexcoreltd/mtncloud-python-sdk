"""Action adapter checks with isolated runner files and mocked MTN responses."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from mtn_cloud import ClientSettings, MtnCloudClient
from mtn_cloud.transport import HttpResponse
from tools import github_action as action

TOKEN = "unit-action-token"
PROVIDER_SECRET = "provider-password-must-not-leak"


@pytest.fixture(autouse=True)
def runner_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith((action.PREFIX, "MTN_CLOUD_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    temporary = tmp_path / "runner-temp"
    temporary.mkdir()
    monkeypatch.setenv("RUNNER_OS", "Linux")
    monkeypatch.setenv("RUNNER_TEMP", str(temporary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    monkeypatch.setenv(action.PREFIX + "TOKEN", TOKEN)
    monkeypatch.setenv("MTN_CLOUD_TOKEN", "ignored-ambient-token")


def output_values() -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in Path(os.environ["GITHUB_OUTPUT"]).read_text().splitlines()
    )


def prepared(monkeypatch: pytest.MonkeyPatch) -> Path:
    assert action.prepare() == 0
    directory = Path(output_values()["work-dir"])
    monkeypatch.setenv(action.PREFIX + "WORK_DIR", str(directory))
    return directory


def run(transport: Mock) -> int:
    def factory(settings: ClientSettings) -> MtnCloudClient:
        return MtnCloudClient(settings=settings, transport=action.ReadOnlyTransport(transport))

    return action.execute(client_factory=factory)


def test_prepare_isolated_private_configuration_does_not_store_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = prepared(monkeypatch)
    assert directory.parent == Path(os.environ["RUNNER_TEMP"])
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    config = directory / "config.json"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert TOKEN not in config.read_text()
    assert json.loads(config.read_text())["argv"] == [
        "--base-url=https://console.cloud.mtn.ng",
        "--timeout=30.0",
        "--output=json",
        "inventory",
    ]


@pytest.mark.parametrize(
    "key,value",
    [
        ("COMMAND", "apply"),
        ("COMMAND", "inventory; echo bad"),
        ("TOKEN", ""),
        ("TOKEN", "line\n::error::injected"),
        ("BASE_URL", "http://example.test"),
        ("BASE_URL", "https://user:secret@example.test"),
        ("BASE_URL", "https://example.test/api"),
        ("BASE_URL", "https://example.test?secret=value"),
        ("BASE_URL", "https://example.test:99999"),
        ("TIMEOUT", "NaN"),
        ("TIMEOUT", "inf"),
        ("TIMEOUT", "0"),
        ("TIMEOUT", "301"),
        ("GROUP", "line\n::set-output name=x::bad"),
        ("NAME", "unexpected-plan-input"),
    ],
)
def test_invalid_inputs_fail_before_sdk_or_work_directory_creation(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    monkeypatch.setenv(action.PREFIX + key, value)
    with pytest.raises(action.InputError):
        action.prepare()
    assert list(Path(os.environ["RUNNER_TEMP"]).iterdir()) == []


def test_mask_escapes_workflow_command_data(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(action.PREFIX + "TOKEN", "first%\n::error::second\r")
    with pytest.raises(action.InputError):
        action.mask_token()
    assert capsys.readouterr().out == "::add-mask::first%25%0A::error::second%0D\n"


def test_plan_required_inputs_and_inventory_only_are_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(action.PREFIX + "COMMAND", "plan")
    with pytest.raises(action.InputError, match="requires"):
        action.configuration()
    monkeypatch.setenv(action.PREFIX + "ONLY", "instances")
    with pytest.raises(action.InputError, match="only"):
        action.configuration()


def test_shell_and_cli_metacharacters_remain_literal_option_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = f"--apply $(touch {tmp_path / 'must-not-exist'}) `echo bad`"
    monkeypatch.setenv(action.PREFIX + "GROUP", payload)
    assert f"--group={payload}" in action.configuration()["argv"]
    assert not (tmp_path / "must-not-exist").exists()


def test_inventory_uses_cli_and_filters_artifact_and_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(action.PREFIX + "ONLY", "instances")
    directory = prepared(monkeypatch)
    transport = Mock()
    transport.request.return_value = HttpResponse(
        200,
        {},
        {
            "instances": [
                {
                    "id": 1,
                    "name": f"prefix-{TOKEN}",
                    "status": "running",
                    "statusMessage": PROVIDER_SECRET,
                    "description": PROVIDER_SECRET,
                    "config": {"password": PROVIDER_SECRET},
                    "layout": {"password": PROVIDER_SECRET},
                    "tags": [{"name": "secret", "value": PROVIDER_SECRET}],
                }
            ]
        },
    )
    assert run(transport) == 0
    artifact = (directory / "result.json").read_text()
    document = json.loads(artifact)
    assert document["schema"] == "mtncloud.action/v1" and document["exit_code"] == 0
    section = document["result"]["resources"]["instances"]
    assert section["count"] == 1
    item = section["items"][0]
    assert (item["id"], item["name"], item["status"]) == (1, "prefix-[REDACTED]", "running")
    assert not {"config", "tags", "layout", "description", "status_message"}.intersection(item)
    assert TOKEN not in artifact and PROVIDER_SECRET not in artifact
    assert stat.S_IMODE((directory / "result.json").stat().st_mode) == 0o600
    summary = Path(os.environ["GITHUB_STEP_SUMMARY"]).read_text()
    assert "| instances | 1 |" in summary and TOKEN not in summary and "prefix-" not in summary
    captured = capsys.readouterr()
    assert PROVIDER_SECRET not in captured.out + captured.err
    assert "prefix-" not in captured.out
    assert output_values()["exit-code"] == "0"
    assert transport.request.call_args.args == ("GET", "/instances")
    transport.close.assert_called_once()


@pytest.mark.parametrize("partial,expected", [(True, 3), (False, 6)])
def test_failures_preserve_codes_with_sanitized_result_files(
    monkeypatch: pytest.MonkeyPatch,
    partial: bool,
    expected: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(action.PREFIX + "ONLY", "instances,networks" if partial else "instances")
    directory = prepared(monkeypatch)
    transport = Mock()
    responses = [HttpResponse(403, {}, {"message": PROVIDER_SECRET}, request_id="req-action")]
    if partial:
        responses.insert(0, HttpResponse(200, {}, {"instances": [{"id": 1}]}))
    transport.request.side_effect = responses
    assert run(transport) == expected
    artifact = (directory / "result.json").read_text()
    document = json.loads(artifact)
    assert document["exit_code"] == expected and PROVIDER_SECRET not in artifact
    error = document["result"]["resources"]["networks"]["error"] if partial else document["error"]
    assert error["status_code"] == 403 and error["request_id"] == "req-action"
    assert output_values()["exit-code"] == str(expected)
    assert PROVIDER_SECRET not in capsys.readouterr().out


def test_plan_calls_existing_resolver_with_get_requests_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, item in {
        "COMMAND": "plan",
        "NAME": "api-01",
        "TYPE_CODE": "alma",
        "GROUP": "621",
        "SERVICE_PLAN": "small",
    }.items():
        monkeypatch.setenv(action.PREFIX + key, item)
    directory = prepared(monkeypatch)
    transport = Mock()
    transport.request.side_effect = [
        HttpResponse(200, {}, {"group": {"id": 621, "zones": [{"id": 4, "name": "AZ1"}]}}),
        HttpResponse(
            200,
            {},
            {
                "instanceTypes": [
                    {
                        "id": 10,
                        "code": "alma",
                        "instanceTypeLayouts": [{"id": 20, "name": "default"}],
                    }
                ]
            },
        ),
        HttpResponse(200, {}, {"data": [{"id": 214, "value": "pool-214"}]}),
        HttpResponse(200, {}, {"plans": [{"id": 30, "name": "small"}]}),
    ]
    assert run(transport) == 0
    document = json.loads((directory / "result.json").read_text())
    assert document["result"]["schema"] == "mtncloud.plan/v1"
    assert document["result"]["dry_run"] is True
    assert document["result"]["resolved"]["plan"] == 30
    assert all(call.args[0] == "GET" for call in transport.request.call_args_list)


def test_caller_env_and_dotenv_do_not_override_action_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(action.PREFIX + "ONLY", "instances")
    prepared(monkeypatch)
    (tmp_path / ".env").write_text("MTN_CLOUD_TOKEN=other\nMTN_CLOUD_VERIFY_SSL=false\n")
    monkeypatch.setenv("MTN_CLOUD_TOKEN", "ambient-secret")
    monkeypatch.setenv("MTN_CLOUD_VERIFY_SSL", "false")
    monkeypatch.setenv("MTN_CLOUD_API_PREFIX", "/wrong-api")
    monkeypatch.setenv("mtn_cloud_timeout", "-5")
    transport = Mock()
    transport.request.return_value = HttpResponse(200, {}, {"instances": []})
    seen = []

    def factory(settings: ClientSettings) -> MtnCloudClient:
        seen.append(settings)
        return MtnCloudClient(settings=settings, transport=transport)

    assert action.execute(client_factory=factory) == 0
    assert seen[0].token_value() == TOKEN and seen[0].verify_ssl is True
    assert seen[0].api_prefix == "/api" and seen[0].max_retries == 1
    assert transport.request.call_args.kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert Path.cwd() == tmp_path


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_transport_rejects_mutations_before_network(method: str) -> None:
    transport = Mock()
    guard = action.ReadOnlyTransport(transport)
    with pytest.raises(RuntimeError):
        guard.request(method, "/instances", json={"name": "never-created"})
    transport.request.assert_not_called()


def test_malformed_cli_result_fails_closed_with_result_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mtn_cloud import cli

    directory = prepared(monkeypatch)

    def fake_cli(*args: Any, **kwargs: Any) -> int:
        print(json.dumps({"schema": "wrong", "secret": PROVIDER_SECRET}))
        return 0

    monkeypatch.setattr(cli, "main", fake_cli)
    assert action.execute() == 1
    artifact = (directory / "result.json").read_text()
    assert PROVIDER_SECRET not in artifact and json.loads(artifact)["result"] is None


def test_preflight_runs_as_isolated_standalone_script() -> None:
    result = subprocess.run(
        [sys.executable, "-I", str(Path(action.__file__).resolve()), "prepare"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and "inputs validated" in result.stdout
    assert result.stderr == ""
