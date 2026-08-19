"""The git tag is the only source of version truth (spec 11.1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import stamp_version

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.0", "1.2.0"),
        ("v0.1.0", "0.1.0"),
        ("v10.20.30", "10.20.30"),
        ("v1.2.0-rc1", "1.2.0-rc1"),
        ("refs/tags/v1.2.0", "1.2.0"),
    ],
)
def test_the_version_comes_off_the_tag(tag: str, expected: str) -> None:
    assert stamp_version.version_from_tag(tag) == expected


@pytest.mark.parametrize("tag", ["1.2.0", "v1.2", "vfoo", "v1.2.0.3", "", "va.b.c"])
def test_a_tag_that_is_not_a_version_is_refused(tag: str) -> None:
    with pytest.raises(ValueError):
        stamp_version.version_from_tag(tag)


@pytest.mark.parametrize(
    ("version", "prerelease"),
    [("1.2.0", False), ("1.2.0-rc1", True), ("1.2.0-beta.2", True)],
)
def test_a_dash_in_the_version_means_pre_release(version: str, prerelease: bool) -> None:
    assert stamp_version.is_prerelease(version) is prerelease


def test_the_exe_file_version_drops_the_pre_release_part() -> None:
    # Windows file properties hold four numbers and nothing else.
    assert stamp_version.file_version_tuple("1.2.0-rc1") == (1, 2, 0, 0)
    assert stamp_version.file_version_tuple("1.2.0") == (1, 2, 0, 0)


def test_the_generated_module_carries_the_real_version() -> None:
    source = stamp_version.version_module_source("1.2.0")

    namespace: dict[str, object] = {}
    exec(compile(source, "_version.py", "exec"), namespace)

    assert namespace["VERSION"] == "1.2.0"
    assert namespace["APP_NAME"] == "FarmsyncSolver"


def test_the_generated_module_matches_the_committed_one_apart_from_the_version() -> None:
    # The committed file is the placeholder the dev checkout keeps (spec 11.1).
    committed = (ROOT / "farmsync_solver" / "_version.py").read_text(encoding="utf-8")

    assert stamp_version.version_module_source("0.0.0-dev") == committed


def test_the_exe_version_file_is_valid_python_and_holds_both_numbers() -> None:
    source = stamp_version.version_file_source("1.2.0-rc1")

    assert "filevers=(1, 2, 0, 0)" in source
    assert "1.2.0-rc1" in source
    assert "FarmsyncSolver" in source
    compile(source, "file_version_info.txt", "exec")


def test_it_writes_both_files_and_reports_the_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = tmp_path / "_version.py"
    version_file = tmp_path / "file_version_info.txt"

    code = stamp_version.main(
        ["v1.2.0-rc1", "--module", str(module), "--version-file", str(version_file)]
    )

    assert code == 0
    assert 'VERSION = "1.2.0-rc1"' in module.read_text(encoding="utf-8")
    assert "filevers=(1, 2, 0, 0)" in version_file.read_text(encoding="utf-8")

    printed = capsys.readouterr().out
    assert "version=1.2.0-rc1" in printed
    assert "numeric=1.2.0" in printed
    assert "prerelease=true" in printed


def test_a_full_release_tag_reports_prerelease_false(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stamp_version.main(
        [
            "v1.2.0",
            "--module",
            str(tmp_path / "_version.py"),
            "--version-file",
            str(tmp_path / "vf.txt"),
        ]
    )

    assert "prerelease=false" in capsys.readouterr().out


def test_a_bad_tag_fails_the_build(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        stamp_version.main(
            ["not-a-tag", "--module", str(tmp_path / "a.py"), "--version-file", str(tmp_path / "b")]
        )


@pytest.mark.parametrize(
    ("version", "numeric"),
    [("1.2.0", "1.2.0"), ("1.2.0-rc1", "1.2.0"), ("10.20.30-beta.2", "10.20.30")],
)
def test_the_numeric_version_drops_the_pre_release_part(version: str, numeric: str) -> None:
    assert stamp_version.numeric_version(version) == numeric
