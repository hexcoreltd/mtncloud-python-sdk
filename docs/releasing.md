# Releasing `mtncloud-python-sdk`

Releases are created from annotated version tags. The release workflow builds
the package once, attaches those distributions to the GitHub Release, and
publishes the same files to PyPI.

## Maintainer checklist

Before creating a release:

1. Confirm the working tree is clean and the default branch is current.
2. Update `version` in `pyproject.toml`, `__version__` in
   `src/mtn_cloud/_version.py`, and the README version badge.
   `tests/test_version.py` fails if they disagree.
3. Update `CHANGELOG.md` with the release date and user-visible changes.
4. Run the local checks:

   ```bash
   uv sync --extra dev
   uv run pytest -q
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy src/mtn_cloud
   uv build
   git diff --check
   ```

5. Commit the release preparation changes and merge them into `main`.
6. Create and push an annotated tag whose version exactly matches
   `pyproject.toml`:

   ```bash
   git tag -a v0.2.0 -m "Release v0.2.0"
   git push origin v0.2.0
   ```

## What CI does

For a tag beginning with `v`, the release workflow:

1. Installs the locked development environment with `uv`.
2. Runs formatting, lint, type, test, and diff checks.
3. Confirms the tag is `vMAJOR.MINOR.PATCH` and matches the project version.
4. Builds and validates the source distribution and wheel.
5. Creates a GitHub Release with generated notes and attached distributions.
6. Publishes those exact artifacts to PyPI using OIDC trusted publishing.

Manual dispatch is available only for TestPyPI package validation. Production
PyPI publication requires a version tag.

## GitHub configuration

The repository should have these environments configured:

- `pypi`: protected environment with the PyPI trusted-publisher workflow and
  environment name configured exactly as used by the workflow.
- `testpypi`: protected environment configured for TestPyPI trusted publishing.

Recommended repository protections:

- Require pull requests before merging into `main`.
- Require the `Quality checks` and all matrix `Tests` checks.
- Restrict tag creation for release tags to maintainers.
- Require a review for the `pypi` environment.
- Keep GitHub Actions permissions read-only by default.

## Recovery

If validation fails, fix the source and create a new version tag. Do not reuse
or move a published tag. If a GitHub Release was created but PyPI publication
failed, rerun the failed workflow only after confirming that the artifacts and
trusted-publisher configuration are correct.
