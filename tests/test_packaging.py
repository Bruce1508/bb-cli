"""Tests for Day 13 packaging deliverables."""
from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).parent.parent


def test_pyproject_has_classifiers():
    """pyproject.toml must have at least 5 classifiers including Python and Education."""
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    classifiers = data["project"].get("classifiers", [])
    assert len(classifiers) >= 5, f"Expected >=5 classifiers, got {len(classifiers)}"
    assert any("Python :: 3" in c for c in classifiers), "Missing 'Programming Language :: Python :: 3'"
    assert any("Education" in c for c in classifiers), "Missing Education classifier"


def test_pyproject_has_project_urls():
    """pyproject.toml must have [project.urls] with Homepage, Repository, and Issues."""
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    urls = data["project"].get("urls", {})
    assert "Homepage" in urls, "Missing Homepage URL"
    assert "Repository" in urls, "Missing Repository URL"
    assert "Issues" in urls, "Missing Issues URL"


def test_setup_browsers_command_exists():
    """bb setup-browsers --help must exit 0 and mention chromium."""
    from typer.testing import CliRunner
    from bb.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["setup-browsers", "--help"])
    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert "chromium" in result.output.lower(), "Help text must mention chromium"


def test_browser_missing_raises_runtime_error():
    """_launch_browser() must raise RuntimeError with actionable message when browser missing."""
    from unittest.mock import MagicMock
    import pytest
    from bb.adapters.blackboard_ultra import _launch_browser

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch.side_effect = Exception(
        "Executable doesn't exist at /Users/test/.cache/ms-playwright/chromium"
    )

    with pytest.raises(RuntimeError, match="Chromium not found. Run: bb setup-browsers"):
        _launch_browser(mock_playwright, headless=True)


def test_ci_workflow_file_exists():
    """.github/workflows/ci.yml must exist."""
    ci_path = _ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists(), f"CI workflow not found at {ci_path}"


def test_ci_workflow_has_required_steps():
    """CI workflow must contain lint (ruff check), test (pytest), and build (uv build) steps."""
    ci_path = _ROOT / ".github" / "workflows" / "ci.yml"
    content = ci_path.read_text()
    assert "ruff check" in content, "CI must run ruff check"
    assert "pytest" in content, "CI must run pytest"
    assert "uv build" in content, "CI must run uv build"
