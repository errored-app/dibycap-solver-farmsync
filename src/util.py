import json
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "input"

with open(INPUT / "config.json", encoding="utf-8") as f:
    _config = json.load(f)


class Util:
    @staticmethod
    def config() -> dict:
        return _config

    @staticmethod
    def short(s: str, n: int = 18) -> str:
        return s if len(s) <= n else s[:n - 1] + "..."
