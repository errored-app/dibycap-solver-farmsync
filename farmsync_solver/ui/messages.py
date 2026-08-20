"""The one error-code -> friendly-sentence table.

Spec 9.7: every word the user reads about a failure comes from here. The engine,
the key checks and the updater hold stable codes and `Headline` members only, and
this module is the one place either becomes English (ADR 0005). Rules for the
wording:

- plain words, no jargon, no error code, no key value;
- say what to do next where there is something to do.
"""
from __future__ import annotations

from typing import Any

from .. import credit
from ..engine.snapshot import Headline, Result
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
HOME_STOP = "Stop"
HOME_STOPPING = "Stopping…"
HOME_SETTINGS = "Settings"
HOME_CHECKING = "Checking your credit…"
HOME_NO_RUNS = "No runs yet."
HOME_DETAILS = "Details"
HOME_FAILED_ONLY = "Show only the ones that failed."
HOME_ROUND = "Round"
HOME_JOINED = "Joined"
HOME_SOLVED = "Captchas solved"
HOME_FAILED = "Could not check"
CREDIT_UNKNOWN = "Credit unknown"

TABLE_STATUS = "Status"
TABLE_ACCOUNT = "Account"
TABLE_DETAIL = "Detail"
TABLE_ELAPSED = "Elapsed"

CLOSE_QUESTION = "A run is going. Stop it and close?"
CLOSE_YES = "Stop and close"
CLOSE_NO = "Keep running"

# What each headline of a run reads as. The engine sets the member; the sentence
# never leaves this module (ADR 0005).
FOR_HEADLINE: dict[Headline, str] = {
    Headline.STARTING: "Getting ready…",
    Headline.DISCOVERING: "Finding accounts…",
    Headline.SOLVING: "Checking accounts…",
    Headline.RESTING: "Waiting for the next round.",
    Headline.NO_ACCOUNTS: "No accounts to check this round.",
    # No "in a minute": the rest countdown right under this line already says when.
    Headline.NO_FARMSYNC: "Could not reach farmsync. Trying again.",
    # The two sentences of the Waiting state (ADR 0003). Two, not one: someone
    # whose wifi is off must not read that the service is paused.
    Headline.WAITING_PAUSED: "The captcha service is paused. Waiting for it to come back…",
    Headline.WAITING_UNREACHABLE: (
        "Could not reach the captcha service. Trying again every minute."
    ),
    Headline.STOPPING: "Stopping. Finishing the accounts already started…",
    Headline.STOPPED: "Stopped.",
    Headline.CRASHED: "Something went wrong and the run stopped.",
}

# What one row's status badge reads (spec 4.2), keyed by the outcome itself. The
# seam runs one way, from here into the engine (ADR 0005), so the enum is in reach.
OUTCOME_WORD: dict[Result, str] = {
    Result.JOINED: "Joined",
    Result.SOLVED: "Captcha solved",
    Result.FAILED: "Could not check",
}

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
SETTINGS_SUPPORT_TITLE = "Something wrong?"
SETTINGS_SUPPORT_NOTE = "Copy the report, then paste it where you ask for help."
SETTINGS_COPY_DIAGNOSTICS = "Copy diagnostics"
SETTINGS_COPIED = "Copied. Paste it where you ask for help."
SETTINGS_OPEN_LOGS = "Open log folder"
SETTINGS_LOGS_FAILED = "Could not open the log folder."
SETTINGS_THEME_TITLE = "Theme"
SETTINGS_THEME_NOTE = "Changes how the app looks. Nothing else changes."
SETTINGS_UPDATES_TITLE = "Updates"
SETTINGS_UPDATES_NOTE = "The app checks for a new version each time it opens."
SETTINGS_CHECK_UPDATES = "Check for updates"
SETTINGS_CHECKING_UPDATE = "Checking…"
SETTINGS_UP_TO_DATE = "You have the newest version."
SETTINGS_CHECK_FAILED = "Could not check for updates. Try again later."

# The update bar of spec 4.2. It sits across the top of Home, never in a dialog:
# a dialog on open teaches people to dismiss without reading.
UPDATE_NOW = "Update now"
UPDATE_DOWNLOADING = "Downloading… the app closes itself when it is ready."
UPDATE_FAILED = "The update could not be downloaded. You can keep using this version."
UPDATE_LOCKED = "Stop the run to update."

# The two words the diagnostics header uses for the key check. Technical, like
# the rest of the report (spec 8.1) — this text is read by the maintainer.
DIAGNOSTICS_KEY_OK = "ok"
DIAGNOSTICS_KEY_UNCHECKED = "not checked yet"


def headline(shown: Headline | ErrorCode | None) -> str:
    """The sentence for the line a snapshot is showing (spec 4.2).

    A member reads out of the table above; a fault reads out of the error table,
    because the headline a run ends on *is* what went wrong. The snapshot before
    any run has neither, and Home puts its own "No runs yet." in the gap.
    """
    if shown is None:
        return ""
    if isinstance(shown, ErrorCode):
        return for_code(shown)
    # No fallback, unlike the rest of this module: a member with no sentence is a
    # missing table row, and the panel would put "No runs yet." on a live run to
    # cover for it. `test_every_headline_has_a_sentence` is what keeps it full.
    return FOR_HEADLINE[shown]


def speed_choice(percent: int) -> str:
    """The label on one Speed button. A percentage, never a thread count."""
    return f"{percent}%"


def outcome_word(result: Result) -> str:
    """The words on one row's status badge."""
    return OUTCOME_WORD.get(result, "")


def elapsed(seconds: float) -> str:
    """How long ago a row landed, as the table's last column.

    Seconds under a minute, then minutes and seconds. A round is ~72 s, so a row
    older than an hour cannot happen and is not spelled out.
    """
    whole = max(0, int(seconds))
    if whole < 60:
        return f"{whole}s"
    return f"{whole // 60}m {whole % 60}s"


def run_progress(done: int, total: int) -> str:
    """The determinate progress line of spec 4.2: "87 of 132"."""
    return f"{done:,} of {total:,}"


def run_rest(seconds_left: int) -> str:
    """The countdown line of spec 4.2, shown while the run rests."""
    return f"Next round in {max(0, seconds_left)}s"


def waiting_for(seconds: float) -> str:
    """How long the run has been sitting in Waiting.

    Its own formatter rather than a wider `elapsed`: a wait has no end of its own
    (ADR 0003) and can run overnight, where a table row cannot. Past the hour the
    seconds digit is dropped — nobody reads it on an hours-old outage, and the
    line it sits on has a countdown ticking beside it anyway.
    """
    whole = max(0, int(seconds))
    if whole < 60:
        return f"{whole}s"
    if whole < 3600:
        return f"{whole // 60}m {whole % 60}s"
    return f"{whole // 3600}h {whole % 3600 // 60}m"


def run_waiting(seconds_waited: float, seconds_left: int | None) -> str:
    """The moving line under the Waiting headline.

    Two facts, in this order: how long this has been going, then when the next
    knock lands. The first is the news — it is what tells a run apart from a
    frozen window — and the second is the heartbeat that proves the app is still
    there between knocks. `seconds_left` of None means the knock is out right
    now, which is the one moment something is actually happening and also the
    one most likely to hang.
    """
    so_far = f"Waiting for {waiting_for(seconds_waited)}."
    if seconds_left is None:
        return f"{so_far} Checking now…"
    return f"{so_far} Checking again in {max(0, seconds_left)}s"


def for_code(code: ErrorCode | None) -> str:
    """The sentence for a code. An unnamed failure reads as an unknown one."""
    return FOR_CODE.get(code, FOR_CODE[ErrorCode.UNKNOWN]) if code else FOR_CODE[ErrorCode.UNKNOWN]


def key_works(balance: dict[str, Any]) -> str:
    """The inline success line of spec 4.1, credit in solves."""
    return f"Key works — {credit.solves(balance):,} captchas left"


def credit_header(balance: dict[str, Any]) -> str:
    """The Home header of spec 4.2: solves first, money second."""
    return credit_text(credit.solves(balance), credit.money(balance))


def update_ready(version: str) -> str:
    """The update bar's headline (spec 12). A version number, no release notes."""
    return f"Version {version} is ready."


def update_found(version: str) -> str:
    """What the manual Check for updates says when it finds one."""
    return f"{update_ready(version)} Go back to Home to install it."


def credit_text(solves: int, money: float) -> str:
    """The same header from two plain numbers, which is what a snapshot carries."""
    return f"{solves:,} captchas left (${money:,.2f})"
