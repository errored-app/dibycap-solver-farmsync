"""The update on offer: what a check found, which stage it is at, and the hand-over.

Spec 12's half that the user can see. `updater` keeps the network and the
installer; everything between the two — the stage the offer is at, how far the
download has got, and the order the app closes in — lives here.

One offer lives for the life of the process, because Home is rebuilt on every
hop back from Settings and a check made on Settings must reach the bar on Home.
`current()` hands it out, and both screens take one as an argument so a test can
build its own.

The dangerous steps are constructor arguments: the offer is told how to install,
how to close and how to leave the event loop, so a test that asserts the
hand-over order never starts an installer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

from nicegui import app as native_app
from nicegui import run

from .. import engine, updater
from ..updater import CheckAnswer, Update
from . import messages

_log = logging.getLogger(__name__)


class UpdateStage(Enum):
    """Where an offered update has got to. One name, not three booleans."""

    READY = "ready"  # waiting for the button
    LOCKED = "locked"  # a run is going, and an install would kill it
    DOWNLOADING = "downloading"
    FAILED = "failed"


# The sentence under the headline. READY has nothing to add, so it says nothing.
UPDATE_NOTE: dict[UpdateStage, str] = {
    UpdateStage.READY: "",
    UpdateStage.LOCKED: messages.UPDATE_LOCKED,
    UpdateStage.DOWNLOADING: messages.UPDATE_DOWNLOADING,
    UpdateStage.FAILED: messages.UPDATE_FAILED,
}

# A failed download may be tried again; the other two dead stages may not.
PRESSABLE = frozenset({UpdateStage.READY, UpdateStage.FAILED})


@dataclass(frozen=True)
class UpdateBar:
    """What the bar across the top of Home shows (spec 4.2, 12).

    Not a dialog, and it never blocks: it says a version is ready and offers one
    button. An update is refused mid-run — an install during a run would kill the
    run — so the button is dead while a run is going and the note says why.
    """

    visible: bool
    headline: str
    note: str
    button_enabled: bool
    progress_visible: bool
    fraction: float


def update_bar(update: Update | None, stage: UpdateStage, fraction: float = 0.0) -> UpdateBar:
    """One found update at one stage, as every word and bar in the strip."""
    return UpdateBar(
        visible=update is not None,
        headline=messages.update_ready(update.version) if update else "",
        note=UPDATE_NOTE[stage],
        button_enabled=stage in PRESSABLE,
        progress_visible=stage is UpdateStage.DOWNLOADING,
        fraction=fraction,
    )


class UpdateOffer:
    """One update on offer, from the check that found it to the app closing."""

    def __init__(
        self,
        is_running: Callable[[], bool] = engine.a_run_is_going,
        install: Callable[[Path], Any] = updater.install,
        shutdown: Callable[[], Any] = native_app.shutdown,
        off_thread: Callable[..., Awaitable[Any]] = run.io_bound,
    ) -> None:
        self._is_running = is_running
        self._install = install
        self._shutdown = shutdown
        self._off_thread = off_thread
        self._update: Update | None = None
        self._stage = UpdateStage.READY
        # Written from the download thread, read by Home's 5 Hz refresh. A float
        # is the whole of the shared state, so no lock buys anything here.
        self._fraction = 0.0

    @property
    def update(self) -> Update | None:
        """The update the last check that reached GitHub found, or None."""
        return self._update

    def stage(self) -> UpdateStage:
        """Which of the four stages the offer is at.

        LOCKED is worked out on every call rather than stored: a run can start
        while the bar is already on screen, and nothing tells the offer it did.

        A run beats a failed download. Both stages have something to say, and
        "Stop the run to update" is the one the user can act on — leaving FAILED
        up would offer a second go that spec 12 refuses to take.
        """
        if self._stage is UpdateStage.DOWNLOADING:
            return UpdateStage.DOWNLOADING
        return UpdateStage.LOCKED if self._is_running() else self._stage

    def view(self) -> UpdateBar:
        """Everything the bar on Home shows right now."""
        return update_bar(self._update, self.stage(), self._fraction)

    async def check(self) -> CheckAnswer:
        """Ask GitHub once, off the event loop, and keep what it found.

        Refused while a run is going: Home is rebuilt on every hop back from
        Settings, so without this a check would run in the middle of a run
        (spec 12).

        A refusal answers in the words of a check that never got through, which
        is all a caller painting a bar can do with it either way. Settings never
        sees one: its button is dead for the whole of a run.
        """
        if self._is_running():
            return self._standing()
        return self.absorb(await self._off_thread(updater.check))

    def absorb(self, answer: CheckAnswer | None) -> CheckAnswer:
        """Take what one check learned, and hand back what now stands.

        A check nobody could make leaves the offer exactly as it was. The bar
        must not vanish because the user went offline: a check that never
        reached GitHub learned nothing about which version is out there, and
        that includes the one an earlier check already found.

        `None` is how NiceGUI answers a call it cancelled, and reads the same
        way.
        """
        if answer is None or not answer.reached_github:
            return self._standing()

        if answer.update != self._update:
            # A different update is a fresh offer: a download that failed for
            # the version before it says nothing about this one.
            self._stage, self._fraction = UpdateStage.READY, 0.0
        self._update = answer.update
        return answer

    async def press(self) -> None:
        """Download, check, hand over. Any failure leaves this version running."""
        update = self._update
        if update is None or self.stage() not in PRESSABLE:
            return

        self._stage, self._fraction = UpdateStage.DOWNLOADING, 0.0
        setup = await self._off_thread(updater.download, update, on_progress=self._downloaded)

        if setup is None:
            self._stage = UpdateStage.FAILED
            return

        self._stage = UpdateStage.READY
        # Asked again, because a download is minutes long and Start was live for
        # every one of them. Installing now would kill the run that just began.
        if self._is_running():
            return

        self._hand_over(setup, update.version)

    def _hand_over(self, setup: Path, version: str) -> None:
        """Spec 12: the app exits itself, and the installer starts as it goes.

        The install is hung on the shutdown rather than called here, so the
        window is already gone when Setup begins replacing the folder the app
        runs from. `updater.install` drops the mutex first, which is what lets
        Setup run at all.
        """
        native_app.on_shutdown(lambda: self._install(setup))
        _log.info("update handed over version=%s", version)
        self._shutdown()

    def _downloaded(self, fraction: float) -> None:
        """Called from the download thread. Home's refresh paints it."""
        self._fraction = fraction

    def _standing(self) -> CheckAnswer:
        """What is on offer, said in the words of a check that never got through."""
        return CheckAnswer(self._update, reached_github=False)


_offer: UpdateOffer | None = None


def current() -> UpdateOffer:
    """The one offer this process holds, made on first use."""
    global _offer
    if _offer is None:
        _offer = UpdateOffer()
    return _offer


def forget() -> None:
    """Drop the offer, so one test's found update cannot outlive it."""
    global _offer
    _offer = None
