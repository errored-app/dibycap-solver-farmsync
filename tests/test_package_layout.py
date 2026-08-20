"""§9.1's layout and §13's no-import-time-file-reads rule."""
from __future__ import annotations

import builtins
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "farmsync_solver"

REQUIRED_FILES = [
    "_version.py",
    "config.py",
    "errors.py",
    "keys.py",
    "logging_setup.py",
    "looks.py",
    "single_instance.py",
    "updater.py",
    "engine/__init__.py",
    "engine/run.py",
    "engine/snapshot.py",
    "engine/farmsync.py",
    "engine/dibycap.py",
    "engine/eligibility.py",
    "ui/__init__.py",
    "ui/app.py",
    "ui/setup.py",
    "ui/home.py",
    "ui/closing.py",
    "ui/settings.py",
    "ui/update_offer.py",
    "ui/messages.py",
    "ui/theme.py",
]

OUR_MODULES = ["farmsync_solver." + name.replace("/", ".")[:-3] for name in REQUIRED_FILES]


@pytest.mark.parametrize("relative", REQUIRED_FILES)
def test_the_module_exists(relative: str) -> None:
    assert (PACKAGE / relative).is_file()


def test_the_engine_never_imports_the_ui() -> None:
    """Spec 9.2's seam, one-way. Held by types now, not by a comment (ADR 0005).

    Run in a fresh interpreter: by the time this file's other tests have run, a
    session has half the app in `sys.modules` and would pass whatever the engine
    imports.
    """
    probe = (
        "import sys, farmsync_solver.engine.run as _; "
        "print(sorted(n for n in sys.modules if n.startswith('farmsync_solver.ui')))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=PACKAGE.parent,
        capture_output=True,
        text=True,
        check=True,
    )

    assert loaded.stdout.strip() == "[]"


def test_the_dev_version_is_a_placeholder() -> None:
    from farmsync_solver import _version

    assert _version.VERSION == "0.0.0-dev"


def test_the_app_name_is_stable() -> None:
    from farmsync_solver import _version

    assert _version.APP_NAME == "FarmsyncSolver"


@pytest.mark.parametrize("module_name", OUR_MODULES)
def test_no_module_reads_a_file_at_import_time(
    module_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError(f"{module_name} read {args[:1]} at import time")

    importlib.import_module(module_name)  # warm the third-party imports first
    # Re-importing gives every later test a second copy of these modules, and a
    # patch on one copy would not be seen by the other. Put the first copies back.
    original = {n: m for n, m in sys.modules.items() if n.startswith("farmsync_solver")}
    for name in original:
        del sys.modules[name]

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)

    try:
        importlib.import_module(module_name)
    finally:
        sys.modules.update(original)
