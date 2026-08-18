import time
from threading import Lock

from colorama import Fore, Style, init

init()

CORAL = "\033[38;5;203m"
RESET = "\033[39m"

LEVELS = {
    "INFO": Fore.LIGHTCYAN_EX,
    "CAPTCHA": Fore.LIGHTCYAN_EX,
    "SOLVED": Fore.LIGHTGREEN_EX,
    "SUCCESS": Fore.LIGHTGREEN_EX,
    "FAIL": CORAL,
}
RESULTS = {"joined": "SUCCESS", "solved": "SOLVED", "fail": "FAIL"}

_lock = Lock()


class Output:
    @staticmethod
    def banner(text: str) -> None:
        with _lock:
            print(f"{Style.BRIGHT}{Fore.LIGHTCYAN_EX}── {text} ──{Style.RESET_ALL}", flush=True)

    @staticmethod
    def error(text: str) -> None:
        with _lock:
            print(f"  {CORAL}{text}{RESET}", flush=True)

    @staticmethod
    def info(text: str) -> None:
        with _lock:
            print(f"  {Style.DIM}{text}{Style.RESET_ALL}", flush=True)

    @staticmethod
    def line(level: str, user: str, detail: str) -> None:
        color = LEVELS[level]
        when = time.strftime("%H:%M:%S")
        with _lock:
            print(f"  {Style.DIM}{when}{Style.RESET_ALL}  {color}[{level}]{RESET:<8}  "
                  f"{user:<20} {Style.DIM}|{Style.RESET_ALL} {color}{detail}{RESET}", flush=True)

    @staticmethod
    def result(user: str, outcome: str, detail: str) -> None:
        Output.line(RESULTS[outcome], user, detail)

    @staticmethod
    def summary(counts: dict) -> None:
        with _lock:
            print(f"\n  {Fore.LIGHTGREEN_EX}{counts['joined']}{RESET} joined  "
                  f"{Fore.LIGHTGREEN_EX}{counts['solved']}{RESET} solved  "
                  f"{CORAL}{counts['fail']}{RESET} fail\n", flush=True)
