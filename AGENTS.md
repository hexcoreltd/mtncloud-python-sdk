# Repository Guidelines

## Project Structure

- `src/mtn_cloud/`: installable SDK package. Modern typed services live under
  `services/`, Pydantic resource models under `models/`, and transport/auth
  infrastructure under `transport/` and `auth/`.
- `tests/`: unit tests and fixtures; `tests/integration/` contains guarded
  MTN Cloud live-contract tests.
- `docs/`: roadmap, live-test, release, and operational documentation.
- `.github/workflows/`: CI and release automation. `examples/` contains usage
  examples.

## Build, Test, and Development Commands

Use `uv` and keep the lockfile synchronized:

```bash
uv sync --locked --extra dev
uv run pytest -q                         # unit tests
uv run pytest -q --cov=mtn_cloud          # tests with coverage
uv run ruff format . && uv run ruff check .
uv run mypy src/mtn_cloud
uv build                                  # wheel and source distribution
```

Run live read-only tests only with explicit credentials and
`MTN_CLOUD_RUN_LIVE_TESTS=1`; mutation tests require a separate explicit
authorization. Never print or commit `.env` credentials.

## Coding Style and Naming

Target Python 3.10+, use four-space indentation, type annotations, and
Pydantic models for API payloads and responses. Ruff enforces formatting,
imports, lint rules, and a 100-character line length. Use `snake_case` for
functions and variables, `PascalCase` for classes, and descriptive service
methods such as `list_subnets` or `wait_until_ready`.

## Testing Guidelines

Tests use pytest and should be deterministic, isolated, and transport-mocked.
Name files `test_<area>.py` and functions `test_<behavior>`. Add regression
tests for every public service or model change. Validate formatting, linting,
mypy, tests, package build, and `git diff --check` before submitting.

## Commits and Pull Requests

Use concise Conventional Commit-style subjects, for example
`feat: add network pool ip lookup` or `ci: restore quality gates`. Keep each
commit focused. Pull requests should explain the API contract covered, list
tests run, document live-contract evidence when applicable, and update
`CHANGELOG.md` and `docs/roadmap.md` for completed features.

## Architecture and Security

Prefer verified MTN Cloud contracts over guessed endpoints. Keep provider
quirks inside service adapters, preserve typed errors and request IDs, and
make destructive operations explicit. The SDK is unofficial; do not present
it as MTN-certified or as regulatory advice.
