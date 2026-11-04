# `mtncloud` CLI v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a read-only `mtncloud` CLI (`list`/`describe` for instances, networks and routers, plus `inventory` and `version`), with stable JSON output and exit codes for CI.

**Architecture:** Two additive SDK methods (`Service.list_all`, `get_by_name`) land first. The CLI is the `mtn_cloud.cli` subpackage. A registry of `ResourceSpec` entries drives one shared `list`/`describe` implementation and `inventory`. Exit codes and output envelopes each live in one module.

**Tech Stack:** Python 3.10+, Pydantic v2, Typer `>=0.27.3,<1.0` (optional `[cli]` extra, which brings `rich`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-04-mtncloud-cli-design.md`. Read it before starting any task. Section numbers below (§N) refer to it.

## Global Constraints

- Python `>=3.10`. Never use `tomllib`, `typing.Self`, or other 3.11+ features.
- Typer is optional: `cli = ["typer>=0.27.3,<1.0"]`. Also add `typer>=0.27.3,<1.0` to the `dev` extra. Regenerate `uv.lock` with `uv lock`.
- Nothing outside `src/mtn_cloud/cli/` may import `typer`, `rich`, or `mtn_cloud.cli`.
- Create Typer apps with `pretty_exceptions_enable=False`.
- No CLI option may accept a credential. Credentials come only from `ClientSettings` (environment variables or `.env`).
- stdout carries only the result document. Diagnostics go to stderr. A failed command writes nothing to stdout.
- Use the schema names exactly: `mtncloud.list/v1`, `mtncloud.describe/v1`, `mtncloud.inventory/v1`, `mtncloud.error/v1`.
- Use the exit codes exactly: 0 OK, 1 internal, 2 usage, 3 partial, 4 not found, 5 ambiguous, 6 auth/permission, 7 API/network, 130 interrupted.
- **Test isolation.** The repo root contains a real `.env` with live credentials. Every CLI test must run with `monkeypatch.chdir(tmp_path)` and must delete `MTN_CLOUD_TOKEN` and `MTN_CLOUD_API_KEY` with `monkeypatch.delenv(..., raising=False)`. Put this in an autouse fixture in `tests/test_cli.py`. Never read or print `.env`.
- Tests are transport-mocked, using `Mock()` transports returning `HttpResponse`, as in `tests/test_modern_client.py`. The only exception is the guarded live test.
- Gates before every commit: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src/mtn_cloud`, `uv run pytest -q`, `git diff --check`.

## Review Focus

1. **`Instance.config` holds user-entered provisioning values.** A user would expect `mtncloud instances describe` not to echo values typed in at provisioning time, such as custom options. The instances `ResourceSpec` therefore excludes `config`. Task 4 pins this. This is a deviation from spec §3, so confirm it with the user.
2. **An API that ignores `offset` while reporting a `total`.** `list_all` must still stop. It counts the items collected itself and stops at `total`, rather than trusting the `meta.offset` value the server returns. Task 1 pins this.
3. **Invalid `--timeout` or `--base-url`** (for example `--timeout 0` or `--base-url console.cloud.mtn.ng`). A user expects a usage error (exit 2) with the validation message, not an internal error (exit 1). Task 3 pins this.
4. **Output piped into a reader that closes early**, as in `mtncloud instances list -o json | head -1`. A user expects a quiet exit with code 0 and no traceback. Task 3 pins this.
5. **`describe` with an all-digit argument.** `describe 1234` treats `1234` as an ID, per §2. When no resource has that ID, the result is exit 4 with a not-found error, even if a resource is named `1234`. Task 4 pins this.

---

### Task 1: `Service.list_all` pagination

**Files:**
- Modify: `src/mtn_cloud/services/base.py` (class `Service`)
- Test: `tests/test_modern_client.py` (append)
- Modify: `CHANGELOG.md` (Unreleased → Added)

**Interfaces:**
- Produces: `Service.list_all(self, *, page_size: int = 100, **filters: Any) -> list[T]`

- [ ] **Step 1: Write failing tests** (all go through `client.instances.list_all(...)` with a mocked transport)
  - `test_list_all_follows_pages_until_total`: two responses, `{"instances":[{"id":1},{"id":2}],"meta":{"total":3}}` then `{"instances":[{"id":3}],"meta":{"total":3}}`. Call with `page_size=2`. Assert the IDs are `[1, 2, 3]`, the second call's params include `"offset": 2, "max": 2`, and there are exactly 2 calls.
  - `test_list_all_stops_on_short_page_without_total`: one response with 1 item, no `meta`, `page_size=2`. Assert 1 call.
  - `test_list_all_stops_on_empty_page`: `{"instances":[],"meta":{"total":10}}`. Assert `[]` and 1 call.
  - `test_list_all_stops_when_api_ignores_offset`: every response is `{"instances":[{"id":1},{"id":2}],"meta":{"offset":0,"total":4}}`, `page_size=2`. Assert exactly 2 calls and 4 items. This is Review Focus 2.
  - `test_list_all_passes_filters_to_every_page`: two pages, called with `zone_id=4`. Assert both calls' params include `"zoneId": 4`.
  - `test_list_all_propagates_mid_pagination_errors`: the first page succeeds and the second is a 503 with `max_retries=0`. Assert `ServerError` is raised.

- [ ] **Step 2: Run and confirm failure**
  Run `uv run pytest -q tests/test_modern_client.py -k list_all`. Expected: FAIL with `AttributeError: ... 'list_all'`.

- [ ] **Step 3: Implement `list_all` in `Service`**
  Get the subclass method with `cast(Callable[..., Page[T]], getattr(self, "list_page"))`. Don't declare `list_page` on the base class: subclass signatures differ, and mypy would report an override error. Loop as follows, tracking `collected` and `offset` locally and ignoring `Page.offset`:
  - Request `list_page(limit=page_size, offset=offset, **filters)`.
  - Stop if the page is empty.
  - Otherwise extend `collected` and add `len(page.items)` to `offset`.
  - Stop if `page.total` is set and `len(collected) >= page.total`.
  - Stop if `page.total` is `None` and `len(page.items) < page_size`.

  Raise `ValueError` if `page_size < 1`.

- [ ] **Step 4: Run and confirm pass**
  Run the Step 2 command again. Expected: 6 passed. Then run the full gate set.

- [ ] **Step 5: CHANGELOG and commit**
  Add to Unreleased → Added: "`list_all()` on modern list services, which follows pagination across all pages."
  ```bash
  git add src/mtn_cloud/services/base.py tests/test_modern_client.py CHANGELOG.md
  git commit -m "feat: add list_all pagination to modern services"
  ```

### Task 2: `get_by_name` on instances, networks, routers

**Files:**
- Modify: `src/mtn_cloud/services/instances.py`, `src/mtn_cloud/services/networks.py`, `src/mtn_cloud/services/routers.py`
- Test: `tests/test_modern_client.py` (append)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `Service.list_all` (Task 1).
- Produces, on each of `InstancesService`, `NetworksService` and `RoutersService`:
  `get_by_name(self, name: str, *, zone_id: int | None = None, group_id: int | None = None) -> <Model>`.
  - No match raises `LookupNotFoundError(f"<Kind> '{name}' was not found")`, where Kind is `Instance`, `Network` or `Router`.
  - Several matches raise `ValueError(f"<Kind> name '{name}' is ambiguous: ids {ids}")`, where `ids` is the sorted list of matching IDs.

- [ ] **Step 1: Write failing tests.** Parametrize each test over `("instances", "instances")`, `("networks", "networks")` and `("routers", "networkRouters")`, giving the service attribute and the list key. The router list key `networkRouters` and path `/networks/routers` were confirmed in `services/routers.py`.
  - `test_get_by_name_returns_exact_match`: items `[{"id":1,"name":"web"},{"id":2,"name":"web-2"}]`. Look up `"web"` with `zone_id=4, group_id=7`. Assert the result is ID 1, and the request params include `"name": "web", "zoneId": 4, "siteId": 7`.
  - `test_get_by_name_raises_lookup_not_found`: items `[{"id":2,"name":"web-2"}]`. Assert `LookupNotFoundError` is raised, matching `"'web' was not found"`.
  - `test_get_by_name_rejects_ambiguous_names`: two items named `"web"` with IDs 5 and 3. Assert a `ValueError` matching `r"ambiguous: ids \[3, 5\]"`, and that it is not an instance of `NotFoundError`.

- [ ] **Step 2: Run and confirm failure**
  Run `uv run pytest -q tests/test_modern_client.py -k get_by_name`. Expected: FAIL with an `AttributeError`.

- [ ] **Step 3: Implement** `get_by_name` on each of the three services, with the Interfaces signature. Call `self.list_all(name=name, zone_id=zone_id, group_id=group_id)`, then filter to `item.name == name`.

- [ ] **Step 4: Run and confirm pass.** Run the Step 2 command again, then the full gate set.

- [ ] **Step 5: CHANGELOG and commit**
  Add to Unreleased → Added: "`get_by_name()` on instances, networks and routers."
  ```bash
  git add src/mtn_cloud/services/{instances,networks,routers}.py tests/test_modern_client.py CHANGELOG.md
  git commit -m "feat: add name lookup to instances, networks and routers"
  ```

### Task 3: CLI foundation — packaging, entry point, exit codes, errors, `version`

**Files:**
- Modify: `pyproject.toml`, `uv.lock`
- Create: `src/mtn_cloud/cli/__init__.py`, `src/mtn_cloud/cli/errors.py`, `src/mtn_cloud/cli/output.py`, `src/mtn_cloud/cli/app.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces in `cli/errors.py`:
  - The constants `EXIT_OK=0`, `EXIT_INTERNAL=1`, `EXIT_USAGE=2`, `EXIT_PARTIAL=3`, `EXIT_NOT_FOUND=4`, `EXIT_AMBIGUOUS=5`, `EXIT_AUTH=6`, `EXIT_API=7` and `EXIT_INTERRUPTED=130`.
  - `class AmbiguousNameError(Exception)` and `class MissingCredentialsError(Exception)`.
  - `exit_code_for(exc: BaseException) -> int`.
  - `error_document(exc: BaseException) -> dict[str, Any]`, which returns the `mtncloud.error/v1` shape from §3. It takes `type` from `type(exc).__name__`, `message` from `str(exc)` for non-SDK errors or `exc.message` for `MtnCloudError`, and the remaining fields from the `MtnCloudError` attributes, defaulting to `None`.
- Produces in `cli/output.py`:
  - `OutputFormat = Literal["json", "table"]`
  - `stdout_is_terminal() -> bool` (patched in tests)
  - `resolve_format(requested: str | None) -> OutputFormat`
  - `emit_json(document: Mapping[str, Any]) -> None`, which writes indented JSON plus a newline to `sys.stdout`
  - `emit_error(exc: BaseException, fmt: OutputFormat) -> None`, which writes to `sys.stderr`
- Produces in `cli/app.py`:
  - `ClientFactory = Callable[[ClientSettings], MtnCloudClient]`
  - `build_app(*, client_factory: ClientFactory, now: Callable[[], datetime]) -> typer.Typer`
  - `CliContext`, a dataclass holding `fmt: OutputFormat`, `debug: bool`, and `client() -> MtnCloudClient`, which raises `MissingCredentialsError` before any request when `settings.token_value()` is `None`
- Produces in `cli/__init__.py`:
  - `main(argv: list[str] | None = None, *, client_factory: ClientFactory | None = None, now: Callable[[], datetime] | None = None) -> int`

- [ ] **Step 1: Packaging.** In `pyproject.toml`:
  - Add `[project.scripts]` with `mtncloud = "mtn_cloud.cli:main"`.
  - Add `cli = ["typer>=0.27.3,<1.0"]` under `[project.optional-dependencies]`.
  - Append `"typer>=0.27.3,<1.0"` to `dev`.

  Then run `uv lock && uv sync --locked --extra dev`. Expected: typer appears in `uv.lock`.

- [ ] **Step 2: Write failing tests in `tests/test_cli.py`.** Include the autouse isolation fixture from Global Constraints. Call `main([...], client_factory=..., now=...)` directly and read output with `capsys`. `main` turns Typer and click exits into return codes, so this is equivalent to the `CliRunner` approach in spec §8 and keeps exit-code handling under test. The factory builds `MtnCloudClient(settings=settings, transport=mock_transport)`.
  - `test_exit_code_mapping` (parametrized), mapping each exception to its code:
    - `AuthenticationError("x")` and `ForbiddenError("x")` → 6
    - `NotFoundError("x")` and `LookupNotFoundError("x")` → 4
    - `AmbiguousNameError("x")` → 5
    - `RateLimitError`, `ServerError`, `TransportError`, `ConflictError`, `ValidationError` and `MtnCloudError` → 7. All of these come from `mtn_cloud.modern_exceptions`. `ValidationError` here is not Pydantic's.
    - `ModernTimeoutError("x", timeout=1)` → 7
    - `MissingCredentialsError()` → 6
    - `ValueError("x")` and `RuntimeError("x")` → 1
    - `KeyboardInterrupt()` → 130
  - `test_error_document_shape`: build `ForbiddenError("denied", status_code=403, request_id="req-1", method="GET", path="/instances")`. Assert `error_document(...) == {"schema": "mtncloud.error/v1", "error": {"type": "ForbiddenError", "message": "denied", "status_code": 403, "request_id": "req-1", "method": "GET", "path": "/instances"}}`.
  - `test_version_prints_package_version`: `main(["version", "-o", "json"])` returns 0, and stdout parses to `{"schema": "mtncloud.version/v1", "version": __version__}`. Add this schema to §3 of the spec when implementing.
  - `test_usage_error_exits_2`: `main(["instances", "--bogus"])` returns 2, stdout is empty, and stderr is non-empty.
  - `test_invalid_settings_are_usage_errors` (parametrized over `["--timeout", "0"]` and `["--base-url", "console.cloud.mtn.ng"]`, each followed by `"version"`): returns 2, and stderr mentions the setting name. This is Review Focus 3.
  - `test_resolve_format`: with `stdout_is_terminal` patched to `True`, `None` gives `"table"`. Patched to `False`, `None` gives `"json"`. `"json"` and `"table"` always win.
  - `test_import_mtn_cloud_does_not_load_typer`: run `subprocess.run([sys.executable, "-c", "import mtn_cloud, sys; print('typer' in sys.modules)"], capture_output=True, text=True)`. Assert stdout is `"False\n"`.
  - `test_main_without_typer_exits_2_with_hint`: `monkeypatch.setitem(sys.modules, "typer", None)`, and delete `mtn_cloud.cli.app` from `sys.modules` if it is present. Assert `main(["version"]) == 2` and that stderr contains `pip install "mtncloud-python-sdk[cli]"`.
  - `test_broken_pipe_exits_quietly`: patch `output.emit_json` to raise `BrokenPipeError`, then run `version -o json`. Assert exit 0 and no `Traceback` in stderr. This is Review Focus 4.
  - `test_console_script_is_declared`: use a regex on `pyproject.toml` for `^mtncloud = "mtn_cloud.cli:main"$`.

- [ ] **Step 3: Run and confirm failure.** Run `uv run pytest -q tests/test_cli.py`. Expected: collection error, because `mtn_cloud.cli` doesn't exist yet.

- [ ] **Step 4: Implement `errors.py`, `output.py`, `app.py` and `__init__.py`**
  - **`exit_code_for`:** check exception types in this order: `KeyboardInterrupt`, `MissingCredentialsError`, `AuthenticationError`/`ForbiddenError`, `NotFoundError`, `AmbiguousNameError`, `MtnCloudError`, then anything else, which gets 1. `NotFoundError` must come before any `ValueError` handling (§4).
  - **`app.py`:** create the root app with `typer.Typer(pretty_exceptions_enable=False, no_args_is_help=True)`.
    - A root callback takes `-o/--output`, `--base-url`, `--timeout` and `--debug`.
    - It builds `ClientSettings(**overrides)`, including only the options that were given, and stores a `CliContext` in `ctx.obj`.
    - It catches Pydantic `ValidationError` from `ClientSettings` and raises `click.BadParameter`, naming the field.
    - Add the `version` command.
  - **`main`:**
    - Inside `try`, import `mtn_cloud.cli.app`. On `ImportError`, print `mtncloud requires the CLI extra: pip install "mtncloud-python-sdk[cli]"` to stderr and return 2.
    - Run the app with `app(args=argv, prog_name="mtncloud", standalone_mode=False)`.
    - Map `click.exceptions.UsageError` (after calling `.show()`) and `click.exceptions.BadParameter` to 2.
    - Map `click.exceptions.Abort` and `KeyboardInterrupt` to 130.
    - Map `BrokenPipeError` to 0: before returning, point stdout at `os.devnull` with `os.dup2`, so the interpreter doesn't fail again at exit.
    - Map every other exception to `emit_error` plus `exit_code_for`. With `--debug`, also print `traceback.format_exc()` to stderr.
    - Commands return their exit code as an int, and `main` returns it.
  - Import `typer` and `rich` only inside `cli/app.py` and `cli/output.py`. `cli/__init__.py` imports nothing from Typer at module level.

- [ ] **Step 5: Run and confirm pass.** Run `uv run pytest -q tests/test_cli.py`, then the full gate set.

- [ ] **Step 6: Commit**
  ```bash
  git add pyproject.toml uv.lock src/mtn_cloud/cli tests/test_cli.py
  git commit -m "feat: add mtncloud CLI foundation with exit-code contract"
  ```

### Task 4: Resource registry, scope, `list` and `describe`

**Files:**
- Create: `src/mtn_cloud/cli/registry.py`, `src/mtn_cloud/cli/scope.py`
- Modify: `src/mtn_cloud/cli/app.py`, `src/mtn_cloud/cli/output.py`
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `list_all` and `get_by_name` (Tasks 1–2), and `CliContext`, `emit_json`, `AmbiguousNameError` and `exit_code_for` (Task 3).
- Produces in `registry.py`:
  - `Column`, a frozen dataclass with `header: str` and `value: Callable[[Any], object]`.
  - `ResourceSpec`, a frozen dataclass with these fields:
    - `name: str`
    - `service: Callable[[MtnCloudClient], Any]`
    - `columns: tuple[Column, ...]`
    - `exclude: frozenset[str] = frozenset()`
  - `REGISTRY: dict[str, ResourceSpec]`, in the order `instances`, `networks`, `routers`.
  - Columns:
    - instances: `ID`, `NAME`, `STATUS`, `IP` (from `ip_address`)
    - networks: `ID`, `NAME`, `CIDR`, `TYPE` (from `type.name`, or empty)
    - routers: `ID`, `NAME`, `STATUS`, `EXTERNAL IP`
  - `exclude` is `frozenset({"config"})` for instances (Review Focus 1) and empty for the others.
- Produces in `scope.py`:
  - `Scope`, a frozen dataclass with `group: str | None`, `zone: str | None`, `group_id: int | None` and `zone_id: int | None`.
  - `resolve_scope(client: MtnCloudClient, *, group: str | None, zone: str | None) -> Scope`. An all-digit value is used as the ID directly. Anything else goes through `client.groups.get_by_name` or `client.zones.get_by_name`, and a `ValueError` from either is re-raised as `AmbiguousNameError(str(exc))`.
- Produces in `output.py`:
  - `dump_item(model: BaseModel, exclude: frozenset[str]) -> dict[str, Any]`, using `model.model_dump(mode="json", exclude=set(exclude))`
  - `list_document(resource: str, items: list[dict[str, Any]]) -> dict[str, Any]`
  - `describe_document(resource: str, item: dict[str, Any]) -> dict[str, Any]`
  - `emit_table(columns: tuple[Column, ...], models: list[Any]) -> None`, a `rich` table on stdout
- Produces in `app.py`: one Typer sub-app per registry entry, each with:
  - `list [--group] [--zone] [--name]`
  - `describe <id-or-name> [--group] [--zone]`

- [ ] **Step 1: Write failing tests** (with mocked transport responses):
  - `test_instances_list_json_envelope`: one page with 2 instances. `main(["instances", "list", "-o", "json"])` returns 0. Stdout equals `{"schema": "mtncloud.list/v1", "resource": "instances", "count": 2, "items": [...]}`. Each item's keys are snake_case, for example `ip_address`.
  - `test_list_uses_scope_ids` (parametrized over the three resources): `--group 7 --zone 4` gives request params with `"siteId": 7` and `"zoneId": 4`, and makes no group or zone lookup call.
  - `test_scope_names_resolve_to_ids`: `--group prod`. The first response is the groups lookup (`{"groups":[{"id":7,"name":"prod"}]}`), and the next request carries `"siteId": 7`.
  - `test_ambiguous_group_exits_5`: two groups are named `prod`. Assert exit 5 and empty stdout.
  - `test_describe_by_name_and_id` (parametrized over resources): `describe web` uses `get_by_name`, and `describe 42` calls `GET <path>/42`. Both return 0 with the `mtncloud.describe/v1` envelope.
  - `test_describe_numeric_argument_is_id`: a 404 on `GET /instances/1234` gives exit 4 and no name lookup. This is Review Focus 5.
  - `test_describe_not_found_exits_4` and `test_describe_ambiguous_exits_5`: both have empty stdout and an error document on stderr.
  - `test_instance_config_is_excluded`: an instance payload with `"config": {"customOptions": {"dbPassword": "s3cret"}}`. Assert `"config"` is not among the item keys and `"s3cret"` does not appear in stdout. This is Review Focus 1.
  - `test_table_output_on_terminal`: with `stdout_is_terminal` patched to `True` and no `-o`, stdout contains the headers `ID`, `NAME` and `STATUS`, and isn't valid JSON.
  - `test_token_never_printed`: set `MTN_CLOUD_TOKEN=tok-SENTINEL-123` through `monkeypatch.setenv`. Run three cases: a 401 response, a transport that raises `RuntimeError`, and the same run with `--debug`. Assert the sentinel appears in neither stdout nor stderr in any case.
  - `test_missing_credentials_exit_6_without_request`: no token in the environment. `main(["instances", "list", "-o", "json"])` returns 6, `transport.request.assert_not_called()` holds, and the stderr error `type` is `MissingCredentialsError`.

- [ ] **Step 2: Run and confirm failure.** Run `uv run pytest -q tests/test_cli.py -k "list or describe or scope or config or table or token"`. Expected: the new tests fail.

- [ ] **Step 3: Implement** `registry.py`, `scope.py`, the new `output.py` functions, and the registry-driven sub-apps in `app.py`.
  - In `describe`, wrap only the `get_by_name` call so that a `ValueError` becomes `AmbiguousNameError`. Let `LookupNotFoundError` through untouched (§4). It is a `ValueError`, so catch `NotFoundError` first and re-raise it.
  - Table versus JSON follows `CliContext.fmt`.

- [ ] **Step 4: Run and confirm pass.** Run `uv run pytest -q tests/test_cli.py`, then the full gate set.

- [ ] **Step 5: Commit**
  ```bash
  git add src/mtn_cloud/cli tests/test_cli.py
  git commit -m "feat: add list and describe commands for instances, networks and routers"
  ```

### Task 5: `inventory`

**Files:**
- Create: `src/mtn_cloud/cli/inventory.py`
- Modify: `src/mtn_cloud/cli/app.py`
- Test: `tests/test_cli.py` (append), `tests/integration/test_live_contract.py` (append)

**Interfaces:**
- Consumes: `REGISTRY`, `ResourceSpec`, `Scope`, `resolve_scope`, `dump_item`, `error_document`, `exit_code_for` and `EXIT_PARTIAL`.
- Produces: `build_inventory(client: MtnCloudClient, scope: Scope, specs: Sequence[ResourceSpec], *, base_url: str, now: Callable[[], datetime]) -> tuple[dict[str, Any], int]`, returning the §3 document and the exit code.
- Produces in `app.py`: `inventory [--only R1,R2] [--group] [--zone]`. Unknown `--only` names raise `click.BadParameter` (exit 2). In table mode, it prints one table per section, with a section's error on stderr.

- [ ] **Step 1: Write failing tests**
  - `test_inventory_document_snapshot`: three mocked list responses and `now=lambda: datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)`. Assert exit 0 and that the stdout JSON equals the full document:
    - `schema`, `generated_at` `"2026-11-04T10:00:00Z"`, `sdk_version` `__version__`, `base_url` `"https://console.cloud.mtn.ng"`, and `scope` `{"group": None, "zone": None}`
    - `resources` with all three keys, each holding `count` and `items`
  - `test_inventory_partial_failure_exits_3`: routers returns a 403. Assert exit 3 and `resources["routers"] == {"error": {...ForbiddenError...}}`, with no `count` or `items` keys. The other two sections are intact.
  - `test_inventory_all_failed_uses_first_error_code`: instances returns a 401, and the others return 503 with `max_retries=0`. Assert exit 6.
  - `test_inventory_only_filters_sections`: `--only networks` gives only a `networks` key, and makes exactly 1 request.
  - `test_inventory_unknown_only_is_usage_error`: `--only volumes` gives exit 2 and empty stdout.
  - `test_inventory_scope_is_recorded`: `--group 7` gives `scope == {"group": "7", "zone": None}`, and requests carry `"siteId": 7`.

- [ ] **Step 2: Run and confirm failure.** Run `uv run pytest -q tests/test_cli.py -k inventory`.

- [ ] **Step 3: Implement** `build_inventory`, catching `Exception` for each section. `KeyboardInterrupt` is not an `Exception`, so it still propagates. Then add the command. Format `generated_at` as `now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.

- [ ] **Step 4: Live test.** Append `test_live_cli_inventory` to `tests/integration/test_live_contract.py`. It uses the existing `live_client` gating (skipped unless `MTN_CLOUD_RUN_LIVE_TESTS=1`) and calls `main(["inventory", "-o", "json"])`. Assert the exit code is in `{0, 3}` and the `schema` is `mtncloud.inventory/v1`. Assert nothing about tenant data, and print nothing.

- [ ] **Step 5: Run and confirm pass.** Run `uv run pytest -q`. Expected: all tests pass, and the live tests are skipped. Then run the full gate set.

- [ ] **Step 6: Commit**
  ```bash
  git add src/mtn_cloud/cli tests/test_cli.py tests/integration/test_live_contract.py
  git commit -m "feat: add mtncloud inventory snapshot command"
  ```

### Task 6: Documentation and release checks

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `docs/roadmap.md`, `docs/superpowers/specs/2026-11-04-mtncloud-cli-design.md`

- [ ] **Step 1: README.** Add a "Command-line interface" section covering:
  - Installation: `pip install "mtncloud-python-sdk[cli]"`, `pipx install`, or `uv tool install`.
  - That credentials come from `MTN_CLOUD_TOKEN` or `.env`.
  - The four commands, with one example each.
  - The default output format (terminal versus pipe).
  - The schemas, with one JSON example.
  - The exit-code table from spec §4.
  - The note that instance `config` is excluded from output.

- [ ] **Step 2: CHANGELOG.** Add to Unreleased → Added: "Read-only `mtncloud` CLI (`[cli]` extra) with `instances`, `networks`, `routers` `list`/`describe`, `inventory`, and `version`; versioned JSON output and documented exit codes."

- [ ] **Step 3: Roadmap and spec.**
  - Mark the read-only inventory CLI done in Milestone 10 and in next action #5 of `docs/roadmap.md`. List `plan` and floating IPs as the next CLI items.
  - In the spec, add the `mtncloud.version/v1` schema and the `config` exclusion to §3, and change its status to "implemented".

- [ ] **Step 4: Release verification.**
  - Run `uv build`, then `unzip -p dist/*.whl '*/entry_points.txt'`. Expected: the output contains `mtncloud = mtn_cloud.cli:main`.
  - Install the wheel into a fresh virtual environment, both without and with `[cli]`:
    - without the extra, `mtncloud version` exits 2 with the install hint
    - with the extra, `mtncloud version -o json` exits 0
  - Run the full gate set on Python 3.10: `UV_PROJECT_ENVIRONMENT=<scratch> uv run --python 3.10 --locked --extra dev pytest -q`.

- [ ] **Step 5: Commit**
  ```bash
  git add README.md CHANGELOG.md docs/
  git commit -m "docs: document the mtncloud CLI"
  ```

- [ ] **Step 6: Independent review.** Before declaring this done, have a separate reviewer agent check the whole change against the spec, the Global Constraints and the Review Focus.
