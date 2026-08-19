"""The Inno Setup script holds §11.3's promises to a non-technical user."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from farmsync_solver import single_instance

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "installer" / "FarmsyncSolver.iss"


@pytest.fixture(scope="module")
def script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def directive(script: str, name: str) -> str:
    match = re.search(rf"^{name}=(.*)$", script, re.MULTILINE)
    assert match is not None, f"{name} is not set"
    return match.group(1).strip()


def test_the_install_needs_no_admin_and_no_uac(script: str) -> None:
    assert directive(script, "PrivilegesRequired") == "lowest"


def test_it_installs_per_user_under_local_appdata(script: str) -> None:
    assert directive(script, "DefaultDirName") == r"{localappdata}\Programs\{#AppName}"


def test_the_app_mutex_is_the_one_the_app_takes(script: str) -> None:
    assert directive(script, "AppMutex") == single_instance.MUTEX_NAME


def test_the_app_id_is_fixed_so_an_update_replaces_the_app(script: str) -> None:
    assert directive(script, "AppId").startswith("{{")


def test_the_setup_file_is_named_for_its_version(script: str) -> None:
    # The updater finds the asset by this pattern, never by array order.
    assert directive(script, "OutputBaseFilename") == "{#AppName}-Setup-{#AppVersion}"


def test_the_version_is_passed_in_and_never_hard_coded(script: str) -> None:
    assert '#define AppVersion "0.0.0-dev"' in script
    assert "#ifndef AppVersion" in script


def test_it_packs_the_whole_built_folder(script: str) -> None:
    assert r'Source: "{#PackedFolder}\*"; DestDir: "{app}"' in script
    assert "recursesubdirs" in script
    assert "createallsubdirs" in script


def test_the_webview2_bootstrapper_is_bundled(script: str) -> None:
    assert 'Source: "MicrosoftEdgeWebview2Setup.exe"' in script


def test_the_webview2_runtime_is_installed_only_when_missing(script: str) -> None:
    (run_line,) = [
        line for line in script.splitlines() if "MicrosoftEdgeWebview2Setup.exe" in line and "Filename:" in line
    ]

    assert "Check: not WebView2Installed" in script
    assert "/silent /install" in run_line


def test_the_runtime_check_reads_every_place_it_can_be_registered(script: str) -> None:
    checks = script[script.index("function WebView2Installed") :]

    assert r"HKLM, 'SOFTWARE\WOW6432Node" in checks
    assert r"HKLM, 'SOFTWARE\Microsoft" in checks
    assert r"HKCU, 'SOFTWARE\Microsoft" in checks


def test_shortcuts_are_made_for_the_start_menu_and_the_desktop(script: str) -> None:
    assert r'Name: "{group}\{#AppName}"' in script
    assert r'Name: "{userdesktop}\{#AppName}"' in script


def test_uninstall_asks_about_saved_keys_once_and_defaults_to_no(script: str) -> None:
    assert script.count("MsgBox") >= 1
    assert "Also delete your saved keys and logs?" in script
    # Suppressible + IDNO: a silent uninstall keeps the keys without asking.
    assert "SuppressibleMsgBox" in script
    assert "MB_DEFBUTTON2" in script
    assert "IDNO) = IDYES" in script


def test_uninstall_deletes_keys_and_logs_together(script: str) -> None:
    """§8.5: logs are user data and follow the same single answer."""
    assert r"{userappdata}\{#AppName}" in script
    assert "DelTree(UserData" in script
