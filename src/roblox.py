import time

from . import solver
from .output import Output
from .util import Util

MAX_ATTEMPTS = 3
BACKOFF_CAP = 2
TERMINAL = ("moderated", "cookie dead", "cookie_dead", "invalid_api_key",
            "insufficient_balance", "key_disabled", "key_expired",
            "service_paused", "banned")


class RobloxError(RuntimeError):
    pass


class Roblox:
    def __init__(self, lock, counter, accounts, counts):
        self.lock = lock
        self.counter = counter
        self.accounts = accounts
        self.counts = counts
        self._account = {}

    def check(self):
        while self._next_account():
            self._run_account()

    def _next_account(self) -> bool:
        idx = self.counter.get_and_increment()
        if idx >= len(self.accounts):
            return False
        self._account = self.accounts[idx]
        return True

    def _user(self) -> str:
        return self._account["username"] or Util.short(self._account["cookie"])

    def _run_account(self):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                outcome, detail = self._solve()
                return self._record(outcome, detail)
            except Exception as e:
                detail = str(e)[:120]
            if any(p in detail.lower() for p in TERMINAL) or attempt == MAX_ATTEMPTS:
                return self._record("fail", detail)
            time.sleep(min(2 ** (attempt - 1), BACKOFF_CAP))

    def _record(self, outcome: str, detail: str):
        with self.lock.get_lock():
            self.counts[outcome] += 1
        Output.result(self._user(), outcome, detail)

    def _solve(self) -> tuple:
        timings = solver.solve(f".ROBLOSECURITY={self._account['cookie']}")
        total = (timings.get("total_ms") or 0) / 1000
        if (timings.get("solve_ms") or 0) > 0:
            return "solved", f"Solved Captcha in {total:.1f}s"
        return "joined", f"Joined in {total:.1f}s"
