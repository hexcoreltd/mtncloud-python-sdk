# `mtncloud` CLI v1 — design

Status: draft for review
Date: 2026-11-04
Roadmap: Milestone 10, immediate next action #5 ("read-only inventory")

## 1. Goal

Ship a read-only `mtncloud` command-line interface, inside this repository and
built on the modern SDK, whose JSON output and exit codes are stable enough for
CI pipelines and the planned GitHub Action to depend on.

### Users and success criteria

The primary user is automation: CI jobs, scripts, and the future GitHub Action.
Operators typing commands at a terminal come second.

v1 is successful when:

- A CI job can list or describe instances, networks, and routers, and capture a
  full inventory snapshot, using only documented JSON and exit codes.
- No credential ever appears in stdout, stderr, or tracebacks.
- Installing the SDK without the `[cli]` extra adds no new dependencies.

### Decisions already made

- The CLI lives in this repo, in Python, rather than a separate Go or Rust
  project. This avoids maintaining a second MTN Cloud API client while API
  contracts are still being verified. Go stays an option if a Terraform
  provider starts, if `morpheus-go-sdk` proves usable (MTN Cloud runs on HPE
  Morpheus), or if users need a single-binary download. A fixed command and
  output contract keeps any later rewrite invisible to CI users.
- Commands are noun-verb, in the style of kubectl.
- Typer is installed as an optional `[cli]` extra, under the safeguards in §6.

### Non-goals for v1

- `plan` (dry-run provisioning), `apply`, or any other command that changes
  resources.
- Floating IPs. The endpoint contract has not been verified yet. Morpheus
  documentation is now candidate evidence, to be confirmed with a read-only
  live check.
- Resources other than instances, networks, and routers.
- The GitHub Action itself.

## 2. Commands

```text
mtncloud <resource> list      [--group G] [--zone Z] [--name N]
mtncloud <resource> describe  <id-or-name> [--group G] [--zone Z]
mtncloud inventory            [--only R1,R2] [--group G] [--zone Z]
mtncloud version
```

v1 resources are `instances`, `networks`, and `routers`.

Global options:

- `-o/--output json|table`
- `--base-url`
- `--timeout`
- `--debug`

Behaviour:

- **Credentials** are read only from `MTN_CLOUD_TOKEN` or `MTN_CLOUD_API_KEY`,
  or from `.env`, through the existing `ClientSettings`. There is deliberately
  no `--token` flag, so tokens never appear in shell history or process
  listings.
- **Default output format** is `table` when stdout is a terminal and `json`
  otherwise. `-o` always overrides it.
- **`--group` and `--zone`** accept a name or a numeric ID. Names are resolved
  with the existing `groups.get_by_name` and `zones.get_by_name`.
- **`describe` arguments** made only of digits are treated as IDs. Anything
  else must exactly match a resource name, within the optional group and zone
  scope.
- **Several name matches** produce an ambiguous-name error (exit 5) that lists
  the matching IDs. The CLI never silently picks one.
- **`--only`** accepts a comma-separated subset of the registered resources.
  Unknown names are a usage error (exit 2).

## 3. Output contract

stdout carries only the result document, and stderr carries only diagnostics.
Each JSON document has a versioned `schema` field. Within a version, fields may
be added but never removed or renamed. Any removal or rename requires a new
schema version.

### `list`

```json
{"schema": "mtncloud.list/v1", "resource": "instances", "count": 2, "items": [{}, {}]}
```

### `describe`

```json
{"schema": "mtncloud.describe/v1", "resource": "instances", "item": {}}
```

### `inventory`

```json
{
  "schema": "mtncloud.inventory/v1",
  "generated_at": "2026-11-04T10:00:00Z",
  "sdk_version": "0.1.0",
  "base_url": "https://console.cloud.mtn.ng",
  "scope": {"group": null, "zone": null},
  "resources": {
    "instances": {"count": 2, "items": []},
    "routers": {"error": {}}
  }
}
```

Each entry in `resources` contains either `count` and `items`, or `error`,
never both. `generated_at` is UTC in RFC 3339 format.

### `version`

```json
{"schema": "mtncloud.version/v1", "version": "<package version>"}
```

### Error (stderr)

```json
{
  "schema": "mtncloud.error/v1",
  "error": {
    "type": "ForbiddenError",
    "message": "...",
    "status_code": 403,
    "request_id": "req-1",
    "method": "GET",
    "path": "/networks/routers"
  }
}
```

Fields that do not apply are `null`. In table mode, the same information is
printed to stderr as one readable line.

### Items

Items are the SDK's Pydantic models dumped as JSON with snake_case field names
(`model_dump(mode="json")`). Output therefore follows the SDK's tested models
rather than raw API responses, and unknown API fields never leak through.

### Tables

Each resource declares its columns in its registry entry, for example
`ID`, `NAME`, `STATUS`, `ZONE` for instances. Tables are for people to read
and are not part of the stable contract.

## 4. Exit codes

| Code | Meaning | Examples |
| --- | --- | --- |
| 0 | Success | |
| 1 | Internal error (a bug in the CLI) | an unexpected exception |
| 2 | Usage error | bad flags; unknown `--only` resource; the `[cli]` extra isn't installed |
| 3 | Partial result | `inventory` where some sections failed |
| 4 | Not found | `describe` with no match; HTTP 404 |
| 5 | Ambiguous name | `describe web` matches several resources |
| 6 | Authentication or permission | missing credentials; HTTP 401 or 403 |
| 7 | API or network failure | 5xx after retries; 429; `TransportError`; other `MtnCloudError` |
| 130 | Interrupted | Ctrl-C |

Rules:

- **One mapping.** Every exception maps to an exit code in a single function,
  `cli/errors.py:exit_code_for`. `NotFoundError`, including
  `LookupNotFoundError`, maps to 4. That check runs before any `ValueError`
  check, because `LookupNotFoundError` is also a `ValueError`.
- **Ambiguous names.** Only a `ValueError` raised by the `get_by_name` call
  inside `describe`, or by scope resolution, is wrapped as an ambiguous-name
  error and maps to 5. Any other `ValueError`, or any other unexpected
  exception, maps to 1.
- **`inventory` failures.** If some sections fail but at least one succeeds,
  the exit code is 3. If every section fails, the exit code is that of the
  first failure in registry order.
- **Missing credentials** are detected before any request is made, and exit
  with 6.
- **Failed commands** write nothing to stdout.
- **Tracebacks** are not printed by default. `--debug` prints a standard
  Python traceback, which lists code lines but not variable values.

## 5. SDK additions

These land first, as separate commits with their own tests and CHANGELOG
entries.

### `Service.list_all(**filters)`

Added in `services/base.py`. It calls the service's existing
`list_page(limit=100, offset=offset, **filters)`, advancing `offset` by the
number of items returned. It stops when the first of these happens:

- `Page.has_more` is false while `total` is known.
- A page returns no items. This guards against an endless loop if the API
  ignores `offset`.
- `total` is unknown and a page returns fewer items than requested.

Errors raised partway through propagate unchanged. `list_all` is only offered
on services whose `list_page` accepts `limit` and `offset`.

### `get_by_name(name, *, zone_id=None, group_id=None)`

Added on `InstancesService`, `NetworksService`, and `RoutersService`. It uses
the API's `name` filter through `list_all`, then requires an exact match
client-side:

- One match returns the model.
- No match raises `LookupNotFoundError`.
- Several matches raise a plain `ValueError` that lists the matching IDs.

## 6. Package layout

All CLI code lives under `src/mtn_cloud/cli/`.

| Module | Responsibility |
| --- | --- |
| `__init__.py` | `main()` entry point. Imports Typer lazily. If Typer is missing, prints `install mtncloud-python-sdk[cli]` to stderr and exits with 2. |
| `app.py` | Typer app created with `pretty_exceptions_enable=False`. Holds the global options callback, builds `MtnCloudClient` from `ClientSettings` (applying `--base-url` and `--timeout`), and registers subcommands from the registry. |
| `registry.py` | `ResourceSpec` dataclass: resource name, a function that returns the service from the client, name lookup, table columns, and supported filters. v1 has three entries. |
| `scope.py` | Resolves `--group` and `--zone` names or IDs to numeric IDs. |
| `inventory.py` | Iterates the registry and builds a section or an error for each resource. Its clock can be replaced in tests. |
| `output.py` | JSON envelopes, `rich` tables, the terminal-versus-pipe choice, and stderr error documents. |
| `errors.py` | `exit_code_for(exc)` and the error document. |

Dependency rules:

- `cli` uses only the SDK's public API: `MtnCloudClient`, `ClientSettings`,
  the services, models, and `mtn_cloud.modern_exceptions`.
- No SDK module imports `mtn_cloud.cli`.
- `import mtn_cloud` must not load `typer` or `rich`.

Packaging changes in `pyproject.toml`:

- `[project.scripts] mtncloud = "mtn_cloud.cli:main"`.
- A `cli = ["typer>=0.27.3,<1.0"]` optional dependency. The loose upper bound
  avoids version conflicts for users who also use Typer. `uv.lock` pins exact
  versions for CI.
- `typer` is also added to the `dev` extra so CI tests and type-checks the CLI.
- `uv.lock` is regenerated.

Typer, `rich`, and their dependencies were checked on 2026-11-04. They are MIT
or BSD licensed and actively maintained, and support Python 3.10+.

## 7. Security

- **No pretty tracebacks.** `pretty_exceptions_enable=False` is set, because
  Typer's pretty tracebacks print local variables. In `CoreClient.request`,
  those include the `Authorization: Bearer` header.
- **Sanitized errors.** Error documents use only the sanitized fields of
  `MtnCloudError`. The path never includes the query string, and errors never
  include headers or the request body.
- **No credential flags.** No option accepts a credential, and `--debug` never
  prints settings.

## 8. Testing

All tests are deterministic and use the mocked `Transport`, with no network
access.

### SDK additions (`tests/test_modern_client.py`)

- `list_all`:
  - follows several pages using `meta.total`
  - stops when the total is unknown and a page comes back short
  - stops when a page comes back empty
  - passes filters through to every page
  - returns errors from the middle of paging unchanged
- `get_by_name`, for each of the three services:
  - an exact match
  - no match, raising `LookupNotFoundError`
  - an ambiguous name, raising a `ValueError` that is not a `NotFoundError`
  - a partial-match name, which is ignored

### CLI (`tests/test_cli.py`, using Typer's `CliRunner`)

- **Envelopes:** snapshot tests for each JSON envelope (`list`, `describe`,
  `inventory`, `error`), with a fixed clock.
- **Exit codes:**
  - each SDK exception class maps to its documented code (parametrized)
  - a usage error exits 2
  - an unknown `--only` resource exits 2
  - missing credentials exit 6, with no request made
  - a partial inventory exits 3
  - an inventory where every section fails exits with the first failure's code
  - Ctrl-C exits 130
- **Output format:**
  - JSON when stdout is not a terminal
  - a table when it is
  - `-o` overrides both
  - stdout stays empty on failure
- **Scope:** group and zone names resolve to IDs and are passed to services.
- **Secrets:** a known token is used through a 401, an unexpected exception,
  and `--debug`. The test asserts the token is absent from stdout and stderr.
- **Packaging:**
  - `import mtn_cloud` does not load `typer`
  - `main()` exits 2 with the install hint when Typer cannot be imported
  - the built wheel declares the `mtncloud` console script

### Live

One read-only `inventory` test in `tests/integration/test_live_contract.py`,
gated by `MTN_CLOUD_RUN_LIVE_TESTS=1`.

### Verification

- The existing CI matrix: Python 3.10, 3.12, and 3.14.
- `ruff format --check`, `ruff check`, `mypy src/mtn_cloud`, `uv build`, and
  `git diff --check`.
- An independent agent review after implementation.

## 9. Documentation

- A README section covering installation, commands, the JSON schemas, and exit
  codes.
- CHANGELOG entries for each SDK addition and for the CLI.
- In `docs/roadmap.md`, mark the read-only inventory CLI as done and keep
  `plan` and floating IPs as the next CLI items.

## 10. Rollout and rollback

- The CLI is a new optional extra and console script. The only behaviour
  change for existing SDK users is two new methods, `list_all` and
  `get_by_name`, which are purely additive.
- Rollback means reverting the CLI commits. No persisted data or existing
  public interface is affected.
- The JSON schemas are versioned from the first release, so later changes can
  evolve them without breaking CI users.
