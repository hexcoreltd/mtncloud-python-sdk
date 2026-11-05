# Control-plane availability monitor

`tools/monitor_control_plane.py` probes `https://console.cloud.mtn.ng/ping`
from a machine outside MTN Cloud. It requires Python 3.10+ and `requests`,
without importing the SDK, reading `.env`, or using MTN credentials.

## Run once

From the repository checkout:

```bash
uv run python tools/monitor_control_plane.py
```

To deploy independently, copy the script to an external host, install
`requests` in its Python environment, and run it directly. The source
distribution includes `tools/`; the SDK wheel does not install this script.

```bash
python -m pip install 'requests>=2.28'
python monitor_control_plane.py
```

Each check emits one JSON line with schema `mtncloud.availability/v1`:

```json
{"schema":"mtncloud.availability/v1","timestamp":"2026-11-05T10:00:00+00:00","url":"https://console.cloud.mtn.ng/ping","status_code":504,"latency_ms":15001.25,"healthy":false,"error":"HTTPStatusError","message":"Endpoint returned a status outside HTTP 200-299.","consecutive_failures":1,"alerting":false,"event":null}
```

Exit codes: `0` for HTTP 200–299, `1` for an unsuccessful probe, `2` for invalid
arguments, and `130` for interruption. Redirects are not followed and count
as unsuccessful. Connection errors have a null `status_code` and expose only
their exception category plus a generic diagnostic, without raw exception
messages or response bodies.

## Watch for failures and recovery

```bash
python monitor_control_plane.py --watch --interval 60 --failure-threshold 3
```

Run this under a process supervisor on an external host. Each cycle waits
the interval after completing its probe. After three consecutive failed
checks, one record contains `"event":"alert"`. Further failures do not repeat
that event. The next successful check emits `"event":"recovery"` and resets
the counter. Successes before the threshold also reset the failure streak.
Watch mode keeps running through unsuccessful probes.

Forward these JSON records through your existing logging or alerting service.
The script itself does not send email or webhook notifications. State is held
in memory and resets on restart; separate one-shot invocations do not share
failure counters or recovery state.

Options include `--url`, `--connect-timeout` (default 5 seconds), and
`--read-timeout` (default 15 seconds). URLs containing credentials, query
strings or fragments are rejected. TLS verification is enabled; normal
Requests proxy and CA configuration remains available. A fresh session and
an explicit anonymous auth handler prevent application credentials and
cookies from carrying between probes.

## Interpret the signal

`healthy` means only that the target returned HTTP 200–299. The response body
is not downloaded or validated. A successful response does not establish
authenticated API readiness, workload health, or connectivity from another
location. In particular, an HTTP 200 loading page still passes this HTTP
check. A healthy `/ping` body contract has not yet been established.

Latency measures the probe through receipt of response headers and connection
cleanup. Connect/read timeouts are Requests socket timeouts, not a strict
wall-clock deadline; DNS resolution and other network behavior can extend
elapsed time. See the [Requests timeout documentation](https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts).

## Test

```bash
uv run pytest tests/test_control_plane_monitor.py -q
uv run mypy tools
```

The automated suite mocks HTTP transport and timing. Healthy MTN response-body
verification remains pending the control plane's recovery.

An unauthenticated live smoke check on 2026-11-05 returned HTTP 403 in
approximately 2.05 seconds; the monitor correctly reported `healthy: false`
and exited 1. This result does not identify the component returning the 403.
