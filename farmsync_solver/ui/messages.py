"""The one error-code -> friendly-sentence table.

Spec 9.7: every word the user reads about a failure comes from here. The engine,
the key checks and the updater hold stable codes only. Rules for the wording:

- plain words, no jargon, no error code, no key value;
- say what to do next where there is something to do.
"""
from __future__ import annotations

from typing import Any

from .. import credit
from ..errors import ErrorCode

FOR_CODE: dict[ErrorCode, str] = {
    ErrorCode.BAD_API_KEY: "That dibycap key was not accepted. Check it and paste it again.",
    ErrorCode.NO_CREDIT: "You are out of credit. Top up to keep going.",
    ErrorCode.SERVICE_PAUSED: "The captcha service is paused. Your key is fine. Try again later.",
    ErrorCode.BAD_FARM_TOKEN: "That farmsync token was not accepted. Check it and paste it again.",
    ErrorCode.NO_INTERNET: "Could not reach the internet. Check your connection and try again.",
    ErrorCode.UNKNOWN: "Something went wrong. Try again in a moment.",
}

NEEDS_API_KEY = "Paste your dibycap key here."
NEEDS_FARM_TOKEN = "Paste your farmsync token here."

SETUP_TITLE = "Welcome"
SETUP_INTRO = "Paste your two keys. The app checks them before it saves them."
SETUP_API_KEY_LABEL = "dibycap key"
SETUP_FARM_TOKEN_LABEL = "farmsync token"
SETUP_BUTTON = "Check and save"
SETUP_CHECKING = "Checking your keys…"

HOME_START = "Start"
HOME_SETTINGS = "Settings"
HOME_CHECKING = "Checking your credit…"
HOME_NO_RUNS = "No runs yet."
CREDIT_UNKNOWN = "Credit unknown"

RUN_STARTING = "Getting ready…"
RUN_DISCOVERING = "Finding accounts…"
RUN_SOLVING = "Checking accounts…"
RUN_RESTING = "Waiting for the next round."
RUN_STOPPING = "Stopping. Finishing the accounts already started…"
RUN_STOPPED = "Stopped."
RUN_NO_ACCOUNTS = "No accounts to check this round."
RUN_NO_FARMSYNC = "Could not reach farmsync. Trying again in a minute."

SETTINGS_TITLE = "Settings"
SETTINGS_BACK = "Back to Home"
SETTINGS_KEYS_TITLE = "Your keys"
SETTINGS_KEYS_NOTE = "Your saved keys are hidden. Paste both again to replace them."
SETTINGS_SAVE_KEYS = "Check and save keys"
SETTINGS_SAVED = "Saved."
SETTINGS_SPEED_LABEL = "Speed"
SETTINGS_SPEED_HELP = "Higher speed works on more accounts at once."
SETTINGS_LOCKED = "Stop the run to change these."
SETTINGS_FORGET = "Forget my keys"
SETTINGS_FORGET_QUESTION = "Delete your saved keys?"
SETTINGS_FORGET_NOTE = "You will have to paste them again next time."
SETTINGS_FORGET_YES = "Forget them"
SETTINGS_CANCEL = "Cancel"


def speed_choice(percent: int) -> str:
    """The label on one Speed button. A percentage, never a thread count."""
    return f"{percent}%"


def run_progress(done: int, total: int) -> str:
    """The determinate progress line of spec 4.2: "87 of 132"."""
    return f"{done:,} of {total:,}"


def run_rest(seconds_left: int) -> str:
    """The countdown line of spec 4.2, shown while the run rests."""
    return f"Next round in {max(0, seconds_left)}s"


def for_code(code: ErrorCode | None) -> str:
    """The sentence for a code. An unnamed failure reads as an unknown one."""
    return FOR_CODE.get(code, FOR_CODE[ErrorCode.UNKNOWN]) if code else FOR_CODE[ErrorCode.UNKNOWN]


def key_works(balance: dict[str, Any]) -> str:
    """The inline success line of spec 4.1, credit in solves."""
    return f"Key works — {credit.solves(balance):,} captchas left"


def credit_header(balance: dict[str, Any]) -> str:
    """The Home header of spec 4.2: solves first, money second."""
    return f"{credit.solves(balance):,} captchas left (${credit.money(balance):,.2f})"
