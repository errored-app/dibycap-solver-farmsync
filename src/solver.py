from time import sleep

from curl_cffi import requests

from .util import Util

API_KEY = Util.config()["api_key"]
API_URL = "https://api.dibycap.com"
POLL_ATTEMPTS = 180
DEFAULT_RETRY_MS = 1000


class SolverError(RuntimeError):
    pass


def solve(cookie: str) -> dict:
    session = requests.Session()
    headers = {"X-API-Key": API_KEY}

    resp = session.post(f"{API_URL}/createTask", json={"cookie": cookie},
                        headers=headers, timeout=15).json()
    task_id = resp.get("task_id")
    if not task_id:
        raise SolverError(resp.get("error") or resp.get("message") or "createTask failed")

    for _ in range(POLL_ATTEMPTS):
        result = session.post(f"{API_URL}/getTask", json={"task_id": task_id},
                              headers=headers, timeout=15).json()
        if result.get("status") in ("pending", "solving", "processing"):
            sleep(max(0.2, (result.get("retry_after_ms") or DEFAULT_RETRY_MS) / 1000))
            continue
        if not result.get("success"):
            raise SolverError(result.get("error") or "solve failed")
        return result.get("timings") or {}

    raise SolverError("timeout")
