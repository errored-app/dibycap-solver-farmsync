r"""Run one full round against the live account, headless, and time it.

Spec 5.4 and 9.2: the Engine has to run from a bare script with no UI and no
config file, so this script is the acceptance test for that. It expects the 132
eligible accounts of spec 2 to finish in roughly 72 s.

    uv run python -m scripts.prove_round

Run it as a module, not as a file: the project is not installed (`package = false`),
so only `-m` puts the repo root on the import path.

The keys come from the saved app config, or from `DIBYCAP_KEY` and
`FARMSYNC_TOKEN` when those are set. Nothing printed can carry a cookie or a key.
"""
from __future__ import annotations

import os
import time

from farmsync_solver import config
from farmsync_solver.engine import Engine
from farmsync_solver.engine.snapshot import RunState

SPEED_PERCENT = 100
POLL_SECONDS = 0.5
GIVE_UP_SECONDS = 600


def main() -> int:
    saved = config.load()
    api_key = os.environ.get("DIBYCAP_KEY") or saved.api_key
    token = os.environ.get("FARMSYNC_TOKEN") or saved.farm_token
    if not api_key or not token:
        print("Need both keys. Set DIBYCAP_KEY and FARMSYNC_TOKEN, or save them in the app.")
        return 1

    engine = Engine()
    rows = 0
    started = time.monotonic()
    engine.start(api_key, token, SPEED_PERCENT)

    # One round is over when the run reaches its first rest. A run that never
    # starts lands back on Idle, and its headline says why.
    while time.monotonic() - started < GIVE_UP_SECONDS:
        rows += len(engine.take_new_rows())
        picture = engine.snapshot()
        if picture.state in (RunState.RESTING, RunState.IDLE):
            break
        time.sleep(POLL_SECONDS)

    seconds = time.monotonic() - started
    engine.stop()
    rows += len(engine.take_new_rows())
    picture = engine.snapshot()

    print(f"state         {picture.state.value}")
    print(f"headline      {picture.headline}")
    print(f"round         {picture.round_number}")
    print(f"accounts      {picture.done} of {picture.total}")
    print(f"joined        {picture.joined}")
    print(f"solved        {picture.solved}")
    print(f"failed        {picture.failed}")
    print(f"rows taken    {rows}")
    print(f"credit left   {picture.estimated_solves} solves (${picture.credit_left:,.2f})")
    print(f"round took    {seconds:.1f}s")
    return 0 if picture.total and picture.done == picture.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
