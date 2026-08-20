"""§9.2: "is a run on?", the one rule every caller reads (CONTEXT.md, "Run state")."""
from __future__ import annotations

import pytest

from farmsync_solver.engine.snapshot import IDLE, RunSnapshot, RunState

RUNNING_STATES = [state for state in RunState if state is not RunState.IDLE]


def test_the_idle_snapshot_is_not_a_run() -> None:
    assert IDLE.is_running is False


@pytest.mark.parametrize("state", RUNNING_STATES, ids=lambda state: state.value)
def test_every_other_state_is_a_run(state: RunState) -> None:
    """Built from `RunState` itself, so a state added later is asked about too."""
    assert RunSnapshot(state=state).is_running is True
