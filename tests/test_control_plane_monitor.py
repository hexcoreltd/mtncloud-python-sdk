"""Standalone availability monitor tests; no requests reach the network."""

import json
from unittest.mock import Mock

import pytest
import requests

from tools import monitor_control_plane as monitor


@pytest.fixture
def send(monkeypatch: pytest.MonkeyPatch) -> Mock:
    sender = Mock()
    monkeypatch.setattr(requests.Session, "send", sender)
    monkeypatch.setattr(
        "requests.sessions.get_netrc_auth",
        Mock(side_effect=AssertionError("Monitor must not load netrc credentials")),
    )
    return sender


def response(status: int) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.raw = Mock()
    result.raw.read.side_effect = AssertionError("Monitor must not read response bodies")
    return result


@pytest.mark.parametrize("status", [200, 204, 299, 301, 302, 401, 403, 500, 504])
def test_http_status_policy_and_request_boundaries(
    send: Mock, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    result_response = response(status)
    send.return_value = result_response
    monkeypatch.setenv("MTN_CLOUD_TOKEN", "test-token-must-not-be-sent")
    monkeypatch.setenv("MTN_CLOUD_API_KEY", "test-key-must-not-be-sent")
    monkeypatch.setattr(monitor.time, "perf_counter", Mock(side_effect=[10, 10.125]))
    result = monitor.probe()
    assert result.healthy is (200 <= status < 300)
    assert result.status_code == status
    assert result.latency_ms == 125
    assert result.timestamp.endswith("+00:00")
    prepared = send.call_args.args[0]
    assert prepared.method == "GET"
    assert prepared.url == monitor.DEFAULT_URL
    assert "Authorization" not in prepared.headers
    assert "Cookie" not in prepared.headers
    assert send.call_args.kwargs["allow_redirects"] is False
    assert send.call_args.kwargs["stream"] is True
    assert send.call_args.kwargs["timeout"] == (5, 15)
    result_response.raw.close.assert_called_once()
    assert send.call_count == 1


@pytest.mark.parametrize(
    "error_type",
    [
        requests.ConnectTimeout,
        requests.ReadTimeout,
        requests.ConnectionError,
        requests.exceptions.SSLError,
    ],
)
def test_connection_failures_are_sanitized(
    send: Mock, error_type: type[requests.RequestException]
) -> None:
    send.side_effect = error_type("sensitive-proxy-password-and-url")
    result = monitor.probe()
    assert result.status_code is None
    assert result.healthy is False
    assert result.error == error_type.__name__
    assert "sensitive" not in str(result)
    assert result.latency_ms >= 0


def test_failure_threshold_and_recovery_transitions() -> None:
    tracker = monitor.FailureTracker(threshold=3)
    assert [tracker.observe(value) for value in [True, False, False, False, False]] == [
        None,
        None,
        None,
        "alert",
        None,
    ]
    assert tracker.consecutive_failures == 4
    assert tracker.observe(True) == "recovery"
    assert tracker.consecutive_failures == 0
    assert tracker.alerting is False
    assert tracker.observe(True) is None
    assert tracker.observe(False) is None


def test_success_resets_failure_streak_before_threshold() -> None:
    tracker = monitor.FailureTracker(threshold=2)
    assert [tracker.observe(value) for value in [False, True, False, False]] == [
        None,
        None,
        None,
        "alert",
    ]


@pytest.mark.parametrize("status", [204, 302, 504])
def test_one_shot_json_and_exit_code(
    send: Mock, capsys: pytest.CaptureFixture[str], status: int
) -> None:
    send.return_value = response(status)
    code = monitor.main([])
    output = capsys.readouterr()
    document = json.loads(output.out)
    assert output.err == ""
    assert document["schema"] == "mtncloud.availability/v1"
    assert document["status_code"] == status
    assert code == (0 if status == 204 else 1)
    assert document["consecutive_failures"] == (0 if status == 204 else 1)


def test_watch_emits_alert_and_recovery_without_repeat_notifications(
    send: Mock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    send.side_effect = [response(status) for status in [504, 504, 504, 200]]
    sleeper = Mock(side_effect=[None, None, None, KeyboardInterrupt()])
    monkeypatch.setattr(monitor.time, "sleep", sleeper)
    assert monitor.main(["--watch", "--interval", "30", "--failure-threshold", "2"]) == 130
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["event"] for record in records] == [None, "alert", None, "recovery"]
    assert [record["alerting"] for record in records] == [False, True, True, False]
    assert [record["consecutive_failures"] for record in records] == [1, 2, 3, 0]
    assert all(call.args == (30,) for call in sleeper.call_args_list)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://console.cloud.mtn.ng/ping",
        "https:///ping",
        "https://user:secret@example.test/ping",
        "https://example.test/ping?token=secret",
        "https://example.test/ping#secret",
        "https://example.test:bad/ping",
        "https://example.test/\nping",
    ],
)
def test_bad_url_is_rejected_without_echoing_secrets(
    send: Mock, capsys: pytest.CaptureFixture[str], url: str
) -> None:
    with pytest.raises(SystemExit) as raised:
        monitor.main(["--url", url])
    assert raised.value.code == 2
    assert "secret" not in capsys.readouterr().err
    send.assert_not_called()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--interval", "0"],
        ["--interval", "nan"],
        ["--read-timeout", "inf"],
        ["--connect-timeout", "-1"],
        ["--failure-threshold", "0"],
    ],
)
def test_invalid_configuration_fails_before_probe(send: Mock, arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        monitor.main(arguments)
    assert raised.value.code == 2
    send.assert_not_called()
