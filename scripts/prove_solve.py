r"""Solve one live account and print its outcome.

Spec 5.5 and 9.4: this is the worker body on its own, before the round loop
exists. It proves that one account produces joined / solved / failed plus the raw
dibycap code, and that a terminal error stops instead of retrying.

    uv run python scripts/prove_solve.py

The keys come from the saved app config, or from `DIBYCAP_KEY` and
`FARMSYNC_TOKEN` when those are set. Nothing printed can carry a cookie or a key.
"""
from __future__ import annotations

import os
import time

from farmsync_solver import config
from farmsync_solver.engine.dibycap import Dibycap
from farmsync_solver.engine.farmsync import Farmsync
from farmsync_solver.engine.run import solve_account
from farmsync_solver.errors import AppError, is_terminal


def main() -> int:
    saved = config.load()
    api_key = os.environ.get("DIBYCAP_KEY") or saved.api_key
    token = os.environ.get("FARMSYNC_TOKEN") or saved.farm_token
    if not api_key or not token:
        print("Need both keys. Set DIBYCAP_KEY and FARMSYNC_TOKEN, or save them in the app.")
        return 1

    eligible = Farmsync(token).discover()
    if not eligible:
        print("No eligible account to try.")
        return 1

    account = eligible[0]
    started = time.monotonic()
    try:
        outcome = solve_account(Dibycap(api_key), account)
    except AppError as error:
        print(f"terminal      {is_terminal(error)}")
        print(f"code          {error.code.value}")
        print(f"detail        {error.detail}")
        return 1
    seconds = time.monotonic() - started

    print(f"account       {outcome.account_id}")
    print(f"outcome       {outcome.result.value}")
    print(f"dibycap code  {outcome.detail or '-'}")
    print(f"took          {seconds:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
