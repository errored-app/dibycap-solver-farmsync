"""Types and tests run on every push, not only on the tag that ships.

`tests/test_release_workflow.py` covers the other half: a tag that packs an app
runs these same two commands before it packs anything.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "checks.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    (job,) = workflow["jobs"].values()
    return job["steps"]


@pytest.fixture(scope="module")
def commands(steps: list[dict[str, Any]]) -> str:
    return "\n".join(step.get("run", "") for step in steps)


def test_a_push_and_a_pull_request_both_run_the_checks(workflow: dict[Any, Any]) -> None:
    # `on` is YAML's `True`, which is why it is looked up both ways.
    triggers: Any = workflow.get("on", workflow.get(True))

    assert "push" in triggers
    assert "pull_request" in triggers


def test_the_types_are_checked(commands: str) -> None:
    assert "uv run pyright" in commands


def test_the_tests_are_run(commands: str) -> None:
    assert "uv run pytest" in commands


def test_the_types_are_checked_before_the_tests(steps: list[dict[str, Any]]) -> None:
    """The faster of the two, and a name that does not exist fails both."""
    runs = [step.get("run", "") for step in steps]
    types = next(i for i, run in enumerate(runs) if "pyright" in run)
    tests = next(i for i, run in enumerate(runs) if "pytest" in run)

    assert types < tests


def test_it_runs_on_windows(workflow: dict[Any, Any]) -> None:
    """Half the suite is testing Windows itself: DPAPI, and a named mutex."""
    (job,) = workflow["jobs"].values()

    assert job["runs-on"] == "windows-latest"


def test_the_dependencies_are_the_locked_ones(commands: str) -> None:
    assert "uv sync --frozen" in commands


def test_every_action_is_pinned_to_a_major_version(steps: list[dict[str, Any]]) -> None:
    for step in steps:
        uses = step.get("uses")
        if uses is not None:
            assert "@" in uses, f"{uses} is not pinned"
