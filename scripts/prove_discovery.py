r"""Prove discovery against the live farmsync account.

Spec 6.3 and 9.5: two bulk calls take about 12 s, and the blocklist left 132 of
8,267 accounts on the 2026-08-17 sample. This script measures both today. It is a
maintainer tool, not part of the app, so it is the one place that reads a token
from the environment.

    uv run python -m scripts.prove_discovery

Run it as a module, not as a file: the project is not installed (`package = false`),
so only `-m` puts the repo root on the import path.

The token comes from `FARMSYNC_TOKEN`, or from the saved app config when that
variable is not set. Nothing printed can carry a cookie or a token.
"""
from __future__ import annotations

import os
import time

from farmsync_solver import config
from farmsync_solver.engine import eligibility
from farmsync_solver.engine.farmsync import Farmsync


def main() -> int:
    token = os.environ.get("FARMSYNC_TOKEN") or config.load().farm_token
    if not token:
        print("No farmsync token. Set FARMSYNC_TOKEN or save one in the app.")
        return 1

    client = Farmsync(token)

    started = time.monotonic()
    accounts = client.accounts()  # the two calls `discover()` makes, timed
    devices = client.devices()
    seconds = time.monotonic() - started

    # The old per-device filter, kept only as the "before" figure to compare to.
    today = [a for a in accounts if a.get("enabled") and not a.get("running")]

    print(f"accounts        {len(accounts)}")
    print(f"devices         {len(devices)} ({sum(map(eligibility.is_live, devices))} live)")
    print(f"two bulk calls  {seconds:.1f}s")
    print(f"old filter      {len(today)}")
    print(f"eligible        {len(eligibility.eligible_accounts(accounts, devices))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
