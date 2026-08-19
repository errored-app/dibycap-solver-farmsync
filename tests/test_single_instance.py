"""The startup mutex that makes a second launch impossible (spec 11.3)."""
from __future__ import annotations

import sys

import pytest

from farmsync_solver import single_instance


@pytest.fixture(autouse=True)
def forget_the_handle() -> None:
    single_instance._handle = None


def test_the_name_matches_the_installer_app_mutex() -> None:
    # Inno Setup's AppMutex looks for this exact name, so the two must not drift.
    assert single_instance.MUTEX_NAME == "FarmsyncSolverSingleInstance"


def test_the_first_launch_takes_the_mutex() -> None:
    assert single_instance.claim(lambda name: (42, 0)) is True
    assert single_instance._handle == 42


def test_a_second_launch_is_refused() -> None:
    def create(name: str) -> tuple[int, int]:
        return (42, single_instance.ERROR_ALREADY_EXISTS)

    assert single_instance.claim(create) is False


def test_the_handle_is_kept_so_the_mutex_outlives_the_call() -> None:
    """A closed handle frees the name, and the installer would see nothing running."""
    single_instance.claim(lambda name: (7, 0))

    assert single_instance._handle == 7


def test_a_failed_call_lets_the_app_start() -> None:
    """No mutex is a worse reason to refuse a launch than a possible second copy."""
    assert single_instance.claim(lambda name: (0, 5)) is True


@pytest.mark.skipif(sys.platform != "win32", reason="there is no mutex off Windows")
def test_the_real_windows_call_refuses_a_second_claim() -> None:
    """The fakes above never touch ctypes; this is the only test that does."""
    # A name of its own: the app's real one must stay free while the tests run.
    name = "FarmsyncSolverTestMutex-single-instance"

    try:
        assert single_instance.claim(name=name) is True
        assert single_instance.claim(name=name) is False
    finally:
        single_instance.release()


@pytest.mark.skipif(sys.platform != "win32", reason="there is no mutex off Windows")
def test_releasing_frees_the_name_for_the_installer() -> None:
    name = "FarmsyncSolverTestMutex-release"
    single_instance.claim(name=name)

    single_instance.release()

    assert single_instance._handle is None
    assert single_instance.claim(name=name) is True
    single_instance.release()
