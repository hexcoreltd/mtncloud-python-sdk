import re
from pathlib import Path

from mtn_cloud import __version__
from mtn_cloud.settings import DEFAULT_USER_AGENT

ROOT = Path(__file__).resolve().parents[1]


def test_package_version_matches_project_metadata() -> None:
    # tomllib is unavailable on Python 3.10, so read the single static field directly.
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)

    assert version is not None
    assert __version__ == version.group(1)


def test_default_user_agent_reports_package_version() -> None:
    assert DEFAULT_USER_AGENT == f"mtncloud-python-sdk/{__version__}"


def test_readme_version_badge_matches_package_version() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"badge/version-([0-9A-Za-z.+-]+?)-[0-9a-f]{6}\)", readme)

    assert badge is not None
    assert badge.group(1) == __version__
