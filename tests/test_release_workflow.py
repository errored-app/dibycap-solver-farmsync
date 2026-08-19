"""The release pipeline lives in one workflow file (spec 11.1)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    (job,) = workflow["jobs"].values()
    return job["steps"]


@pytest.fixture(scope="module")
def commands(steps: list[dict[str, Any]]) -> str:
    return "\n".join(step.get("run", "") for step in steps)


def test_only_a_version_tag_starts_a_release(workflow: dict[str, Any]) -> None:
    # `on` is YAML's `True`, which is why it is looked up both ways.
    triggers = workflow.get("on", workflow.get(True))

    assert triggers["push"]["tags"] == ["v*"]


def test_it_builds_on_windows(workflow: dict[str, Any]) -> None:
    (job,) = workflow["jobs"].values()

    assert job["runs-on"] == "windows-latest"


def test_it_may_publish_a_release(workflow: dict[str, Any]) -> None:
    assert workflow["permissions"]["contents"] == "write"


def test_the_dependencies_come_from_the_committed_lock_file(commands: str) -> None:
    assert "uv sync --frozen" in commands


def test_the_version_is_stamped_from_the_tag(commands: str) -> None:
    assert "scripts.stamp_version" in commands
    assert "github.ref_name" in commands


def test_the_build_uses_nicegui_pack_onedir_and_windowed(commands: str) -> None:
    assert "nicegui-pack" in commands
    assert "--onedir" in commands
    assert "--windowed" in commands
    assert "--icon" in commands
    assert "--noconfirm" in commands


def test_the_build_never_falls_back_to_bare_pyinstaller_or_onefile(commands: str) -> None:
    # Spec 11.3 owns the reasons; this only holds the build to them.
    assert "--onefile" not in commands
    for line in commands.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("pyinstaller")
        assert not stripped.startswith("uv run pyinstaller")


def test_the_exe_properties_get_the_same_version(commands: str) -> None:
    # nicegui-pack has no --version-file of its own, so the resource is applied
    # to the built exe afterwards.
    stamped = commands.replace("\\", "/")

    assert "pyi-set_version build/file_version_info.txt" in stamped
    assert "dist/FarmsyncSolver/FarmsyncSolver.exe" in stamped


def test_the_selftest_runs_against_the_built_exe(commands: str) -> None:
    stripped = commands.replace("\\", "/")

    assert "dist/FarmsyncSolver/FarmsyncSolver.exe" in stripped
    assert "--selftest" in stripped


def test_a_failing_selftest_fails_the_release(steps: list[dict[str, Any]]) -> None:
    # A --windowed exe is GUI-subsystem, which PowerShell does not wait on: a
    # direct call would leave $LASTEXITCODE empty and pass whatever happened.
    (selftest,) = [step for step in steps if "--selftest" in step.get("run", "")]
    run = selftest["run"]

    assert "Start-Process" in run
    assert "-Wait" in run
    assert "-PassThru" in run
    assert "throw" in run


def test_checksums_are_published(commands: str, steps: list[dict[str, Any]]) -> None:
    assert "SHA256SUMS.txt" in commands

    (release,) = [step for step in steps if "softprops/action-gh-release" in step.get("uses", "")]
    assert "SHA256SUMS.txt" in release["with"]["files"]


def test_a_dash_in_the_tag_publishes_a_pre_release(steps: list[dict[str, Any]]) -> None:
    (release,) = [step for step in steps if "softprops/action-gh-release" in step.get("uses", "")]

    assert release["with"]["prerelease"] == "${{ steps.version.outputs.prerelease == 'true' }}"


def test_every_action_is_pinned_to_a_major_version(steps: list[dict[str, Any]]) -> None:
    for step in steps:
        uses = step.get("uses")
        if uses is not None:
            assert "@" in uses, f"{uses} is not pinned"


def test_the_installer_is_built_by_iscc(commands: str) -> None:
    stripped = commands.replace("\\", "/")

    assert "iscc.exe" in stripped
    assert "installer/FarmsyncSolver.iss" in stripped


def test_the_installer_gets_the_version_from_the_tag(commands: str) -> None:
    assert "/DAppVersion=${{ steps.version.outputs.version }}" in commands
    assert "/DAppNumericVersion=${{ steps.version.outputs.numeric }}" in commands


def test_a_failed_installer_build_fails_the_release(steps: list[dict[str, Any]]) -> None:
    (build,) = [step for step in steps if "iscc.exe" in step.get("run", "")]

    assert "throw" in build["run"]


def test_the_webview2_bootstrapper_is_fetched_before_the_installer_is_built(
    steps: list[dict[str, Any]],
) -> None:
    runs = [step.get("run", "") for step in steps]
    fetch = next(i for i, run in enumerate(runs) if "MicrosoftEdgeWebview2Setup.exe" in run)
    build = next(i for i, run in enumerate(runs) if "iscc.exe" in run)

    assert fetch < build


def test_the_setup_exe_is_published_and_checksummed(
    steps: list[dict[str, Any]], commands: str
) -> None:
    (release,) = [step for step in steps if "softprops/action-gh-release" in step.get("uses", "")]
    assert "FarmsyncSolver-Setup-${{ steps.version.outputs.version }}.exe" in release["with"]["files"]

    # The checksums are taken after the installer exists, or its line is missing.
    runs = [step.get("run", "") for step in steps]
    build = next(i for i, run in enumerate(runs) if "iscc.exe" in run)
    checksums = next(i for i, run in enumerate(runs) if "SHA256SUMS.txt" in run)
    assert build < checksums


def test_inno_setup_is_pinned_like_every_other_tool(commands: str) -> None:
    assert "choco install innosetup --version=" in commands


def test_the_fetched_bootstrapper_is_checked_before_it_is_packed(
    steps: list[dict[str, Any]],
) -> None:
    """Those bytes ship inside the Setup.exe a user runs."""
    (fetch,) = [step for step in steps if "MicrosoftEdgeWebview2Setup.exe" in step.get("run", "")]

    assert "Get-AuthenticodeSignature" in fetch["run"]
    assert "Microsoft Corporation" in fetch["run"]
    assert "throw" in fetch["run"]
