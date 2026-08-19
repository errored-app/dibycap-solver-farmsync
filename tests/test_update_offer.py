"""§12's offer: the four stages, the bar they paint, and the hand-over.

No window and no network in this file. The offer takes its dangerous steps as
callables, so a test hands it two lists and reads back the order they filled up
in — which is the whole of the hand-over rule.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from farmsync_solver import updater
from farmsync_solver.ui import messages, update_offer
from farmsync_solver.ui.update_offer import UpdateOffer, UpdateStage

UPDATE = updater.Update(
    version="1.2.0",
    setup_name="FarmsyncSolver-Setup-1.2.0.exe",
    setup_url="https://example.test/setup.exe",
    checksums_url="https://example.test/SHA256SUMS.txt",
)
SETUP = Path("FarmsyncSolver-Setup-1.2.0.exe")


async def straight(work: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """The `off_thread` a test gives the offer: the same call, on this thread."""
    return work(*args, **kwargs)


def offering(update: updater.Update | None = UPDATE, **changes: Any) -> UpdateOffer:
    """An offer already holding `update`, with nothing dangerous wired up."""
    changes.setdefault("is_running", lambda: False)
    offer = UpdateOffer(off_thread=straight, **changes)
    offer.absorb(updater.CheckAnswer(update))
    return offer


async def after_a_failed_download(
    monkeypatch: pytest.MonkeyPatch, running: list[bool]
) -> UpdateOffer:
    """An offer at FAILED, got there the way the app gets there: by pressing."""
    monkeypatch.setattr(updater, "download", lambda update, **kwargs: None)
    offer = offering(is_running=lambda: running[0])
    await offer.press()
    assert offer.stage() is UpdateStage.FAILED
    return offer


# --- the bar, as a pure answer ---------------------------------------------


def test_no_update_means_no_bar() -> None:
    assert update_offer.update_bar(None, UpdateStage.READY).visible is False


def test_a_found_update_offers_its_version_and_a_live_button() -> None:
    bar = update_offer.update_bar(UPDATE, UpdateStage.READY)

    assert bar.visible is True
    assert bar.headline == "Version 1.2.0 is ready."
    assert bar.button_enabled is True
    assert bar.note == ""
    assert bar.progress_visible is False


def test_a_run_locks_the_button_and_says_why() -> None:
    bar = update_offer.update_bar(UPDATE, UpdateStage.LOCKED)

    assert bar.button_enabled is False
    assert bar.note == messages.UPDATE_LOCKED


def test_a_download_shows_a_progress_bar_and_no_second_press() -> None:
    bar = update_offer.update_bar(UPDATE, UpdateStage.DOWNLOADING, fraction=0.4)

    assert bar.progress_visible is True
    assert bar.fraction == 0.4
    assert bar.button_enabled is False
    assert bar.note == messages.UPDATE_DOWNLOADING


def test_a_failed_download_says_the_app_still_works_and_offers_another_go() -> None:
    bar = update_offer.update_bar(UPDATE, UpdateStage.FAILED)

    assert bar.note == messages.UPDATE_FAILED
    assert bar.button_enabled is True


# --- what a check leaves behind --------------------------------------------


def test_an_offer_that_found_nothing_shows_no_bar() -> None:
    assert offering(None).view().visible is False


def test_a_check_nobody_could_make_leaves_the_offer_standing() -> None:
    """The bar must not vanish because the user went offline. No network here."""
    offer = offering()

    answer = offer.absorb(updater.CheckAnswer(None, reached_github=False))

    assert offer.view().visible is True
    assert answer.update == UPDATE  # the caller is told what still stands
    assert answer.reached_github is False


def test_a_check_that_reached_github_and_found_nothing_takes_the_bar_down() -> None:
    offer = offering()

    offer.absorb(updater.CheckAnswer(None))

    assert offer.view().visible is False


async def test_a_new_version_clears_the_stage_the_last_one_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A download that failed for the version before says nothing about this one."""
    offer = await after_a_failed_download(monkeypatch, [False])

    offer.absorb(updater.CheckAnswer(updater.Update("1.3.0", "s.exe", "s", "c")))

    assert offer.stage() is UpdateStage.READY
    assert offer.view().headline == "Version 1.3.0 is ready."


async def test_a_run_stops_a_check_being_made_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec 12: a run is not interrupted, not even by a question."""
    asked: list[str] = []
    monkeypatch.setattr(updater, "check", lambda *args, **kwargs: asked.append("asked"))

    answer = await offering(is_running=lambda: True).check()

    assert asked == []
    assert answer.reached_github is False


def test_the_process_holds_one_offer() -> None:
    assert update_offer.current() is update_offer.current()


# --- the four stages -------------------------------------------------------


def test_a_found_update_waits_for_the_button() -> None:
    assert offering().stage() is UpdateStage.READY


def test_a_run_locks_the_offer() -> None:
    assert offering(is_running=lambda: True).stage() is UpdateStage.LOCKED


async def test_a_run_locks_an_offer_whose_download_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FAILED offers another go; a run takes it away again until the run ends."""
    running = [False]
    offer = await after_a_failed_download(monkeypatch, running)

    running[0] = True

    assert offer.stage() is UpdateStage.LOCKED
    assert offer.view().button_enabled is False
    assert offer.view().note == messages.UPDATE_LOCKED


async def test_a_locked_offer_downloads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    downloads: list[Any] = []
    monkeypatch.setattr(updater, "download", lambda update, **kwargs: downloads.append(update))

    await offering(is_running=lambda: True).press()

    # The second go a failed download offers is refused mid-run as well.
    running = [False]
    failed = await after_a_failed_download(monkeypatch, running)
    running[0] = True
    monkeypatch.setattr(updater, "download", lambda update, **kwargs: downloads.append(update))
    await failed.press()

    assert downloads == []


async def test_the_offer_is_downloading_while_the_download_is_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []

    def report_half_way(update: Any, on_progress: Any = None, **kwargs: Any) -> None:
        on_progress(0.5)
        seen.append((offer.stage(), offer.view().fraction))
        return None

    monkeypatch.setattr(updater, "download", report_half_way)
    offer = offering()

    await offer.press()

    assert seen == [(UpdateStage.DOWNLOADING, 0.5)]


async def test_a_failed_download_leaves_the_offer_failed_and_pressable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []
    monkeypatch.setattr(updater, "download", lambda update, **kwargs: None)
    offer = offering(shutdown=lambda: closed.append("closed"))

    await offer.press()

    assert offer.stage() is UpdateStage.FAILED
    assert offer.view().button_enabled is True
    assert closed == []


# --- the hand-over ---------------------------------------------------------


async def test_the_window_goes_before_the_installer_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    closing: list[Callable[[], None]] = []
    monkeypatch.setattr(updater, "download", lambda update, **kwargs: SETUP)
    monkeypatch.setattr(update_offer.native_app, "on_shutdown", closing.append)
    offer = offering(
        install=lambda setup: order.append(f"install {setup.name}"),
        shutdown=lambda: order.append("closed"),
    )

    await offer.press()

    # Nothing touches the installed app until the window is gone.
    assert order == ["closed"]
    closing[-1]()
    assert order == ["closed", f"install {SETUP.name}"]


async def test_a_run_started_during_the_download_stops_the_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A download is minutes long, and Start was live for every one of them."""
    running = [False]
    order: list[str] = []

    def start_a_run_mid_download(update: Any, **kwargs: Any) -> Path:
        running[0] = True
        return SETUP

    monkeypatch.setattr(updater, "download", start_a_run_mid_download)
    offer = offering(
        is_running=lambda: running[0],
        install=lambda setup: order.append("install"),
        shutdown=lambda: order.append("closed"),
    )

    await offer.press()

    assert order == []
    assert offer.stage() is UpdateStage.LOCKED
    assert offer.view().note == messages.UPDATE_LOCKED
