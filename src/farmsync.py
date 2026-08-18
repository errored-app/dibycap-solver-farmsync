import time

import requests

BASE_URL = "https://api.farmsync.cloud"


class FarmsyncError(RuntimeError):
    pass


class Farmsync:
    def __init__(self, token: str):
        self._s = requests.Session()
        self._s.headers["Authorization"] = f"Bearer {token}"
        self._s.trust_env = False

    def _get(self, url: str):
        for attempt in range(3):
            try:
                r = self._s.get(url, timeout=30)
                r.raise_for_status()
                return r
            except requests.Timeout:
                if attempt == 2:
                    raise FarmsyncError("timeout")
                time.sleep(2)
            except requests.RequestException as e:
                raise FarmsyncError(str(e))

    def _devices(self) -> list:
        return _as_list(self._get(f"{BASE_URL}/api/devices/").json())

    def _accounts(self, device_id) -> list:
        return _as_list(self._get(f"{BASE_URL}/api/devices/{device_id}/accounts").json())

    def solvable_accounts(self) -> list:
        raw = []
        for d in self._devices():
            if not d.get("is_enabled"):
                continue
            for a in self._accounts(d.get("id")):
                if a.get("enabled") and not a.get("running"):
                    raw.append(a)
        raw.sort(key=lambda a: not a.get("rejoining", False))
        accounts = []
        for a in raw:
            cookie = a.get("cookie") or a.get(".ROBLOSECURITY") or ""
            if cookie:
                accounts.append({"username": a.get("username") or "", "cookie": cookie})
        return accounts


def _as_list(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list):
                return v
    return []
