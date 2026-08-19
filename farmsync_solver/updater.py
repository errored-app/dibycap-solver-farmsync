r"""GitHub Releases check, download, checksum, run Setup.exe.

Spec 12, and one of the three files allowed to touch the network (spec 9.4).

A plain custom updater: PyUpdater is archived, `pywinsparkle` abandoned, and
`tufup` is a key-management framework out of all proportion to a small tool
shipped from public GitHub Releases.

Two rules shape every function here:

- **Nothing raises.** No internet, a half download and a wrong checksum all read
  the same way — a log line and an answer holding no update — and the app carries
  on with the version it already has. This module is named in spec 9.7 beside
  the ones that raise `AppError`; spec 12 asks for the opposite, and spec 12 wins
  here, because there is nothing for a caller to do about any of these but wait.
- **The installed app is not touched until the new installer is on disk and its
  SHA-256 matches.** Only then does the app drop its mutex and hand over.
"""
from __future__ import annotations

import fnmatch
import hashlib
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from . import single_instance
from ._version import APP_NAME, VERSION
from .logging_setup import default_log_dir

REPOSITORY = "errored-app/dibycap-solver-farmsync"
RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
GITHUB_HEADERS = {"Accept": "application/vnd.github+json"}

# The asset is found by this pattern, never by its place in the array: the order
# GitHub returns assets in is not promised anywhere.
SETUP_PATTERN = f"{APP_NAME}-Setup-*.exe"
CHECKSUMS_NAME = "SHA256SUMS.txt"

TIMEOUT_SECONDS = 30
CHUNK_BYTES = 256 * 1024

# /VERYSILENT: no window at all. /SUPPRESSMSGBOXES: no question nobody can see.
# /NORESTART: no unprompted reboot. CLOSEAPPLICATIONS and RESTARTAPPLICATIONS are
# the Restart Manager safety net; the app exiting itself is the real close.
SILENT_FLAGS = (
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
    "/RESTARTAPPLICATIONS",
)

# 1.2.0, or 1.2.0-rc1. The same shape `scripts/stamp_version.py` writes.
VERSION_SHAPE = re.compile(r"^v?(?P<numbers>\d+\.\d+\.\d+)(?:-(?P<pre>[0-9A-Za-z.-]+))?$")

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Update:
    """One newer release, with both links the download needs."""

    version: str
    setup_name: str
    setup_url: str
    checksums_url: str


@dataclass(frozen=True)
class CheckAnswer:
    """What one check came to.

    `reached_github` is the difference between "you have the newest version" and
    "nobody could be asked". Both leave the app alone, but a user who pressed a
    button must not be told the first when the second happened.
    """

    update: Update | None = None
    reached_github: bool = True

    @property
    def is_current(self) -> bool:
        """The app is the newest version, and we know that for a fact."""
        return self.reached_github and self.update is None


def is_newer(latest: str, current: str) -> bool:
    """Whether `latest` is worth offering over `current`.

    A version nobody can read is never newer: an unreadable tag must not push an
    installer at a user, and an unreadable local version would offer every
    release for ever.
    """
    left, right = _parts(latest), _parts(current)
    if left is None or right is None:
        return False
    return left > right


def find_update(payload: Any, current_version: str = VERSION) -> Update | None:
    """One `releases/latest` payload, as an update to offer — or nothing.

    Both assets must be there. A release with an installer but no `SHA256SUMS.txt`
    cannot be checked, and an installer that cannot be checked is not run.
    """
    if not isinstance(payload, dict):
        return None

    version = str(payload.get("tag_name") or "").lstrip("v")
    if not is_newer(version, current_version):
        return None

    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None

    setup = _asset(assets, lambda name: fnmatch.fnmatch(name, SETUP_PATTERN))
    checksums = _asset(assets, lambda name: name == CHECKSUMS_NAME)
    if setup is None or checksums is None:
        _log.info("release %s has no complete pair of assets", version)
        return None

    return Update(
        version=version,
        setup_name=str(setup.get("name")),
        setup_url=str(setup.get("browser_download_url")),
        checksums_url=str(checksums.get("browser_download_url")),
    )


def check(session: Any | None = None, current_version: str = VERSION) -> CheckAnswer:
    """Ask GitHub once. Every failure answers "nothing found, and we never asked".

    Unauthenticated: 60 requests an hour is ample for one call at startup and one
    behind a button.

    The answer holds only what this call learned. What a failed check leaves
    standing is `ui.update_offer.UpdateOffer.absorb`'s rule, not this one.
    """
    talker = session if session is not None else _new_session()

    try:
        response = talker.get(RELEASE_URL, headers=GITHUB_HEADERS, timeout=TIMEOUT_SECONDS)
        if response.status_code != 200:
            _log.info("update check refused http=%s", response.status_code)
            return CheckAnswer(reached_github=False)
        payload = response.json()
    except Exception as error:  # offline, a timeout, a body that is not JSON
        _log.info("update check failed error=%s", type(error).__name__)
        return CheckAnswer(reached_github=False)

    if not isinstance(payload, dict):
        # A shape nobody expected is a failed call, not a "you are up to date":
        # the app learned nothing about which version is out there.
        _log.info("update check got an unexpected shape")
        return CheckAnswer(reached_github=False)

    found = find_update(payload, current_version)
    _log.info("update check ok found=%s", found.version if found else "none")
    return CheckAnswer(found)


def expected_hash(text: str, name: str) -> str | None:
    """The SHA-256 for one file name in a `SHA256SUMS.txt` body.

    The format is `<hash>  <name>` per line, which is what `Get-FileHash` is
    written into in the release workflow.
    """
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == name:
            return parts[0].lower()
    return None


def download(
    update: Update,
    folder: Path | None = None,
    session: Any | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path | None:
    """Fetch the installer and check it. Returns its path, or None on any trouble.

    The checksum file is fetched **first**: with no hash to check against there is
    no point spending the download, and there is nothing to delete afterwards.
    """
    talker = session if session is not None else _new_session()
    target = _folder(folder) / update.setup_name

    wanted = _checksum_for(talker, update)
    if wanted is None:
        return None

    try:
        digest = _write_body(talker, update.setup_url, target, on_progress)
    except Exception as error:
        _log.info("update download failed error=%s", type(error).__name__)
        _remove(target)
        return None

    if digest != wanted:
        _log.warning("update checksum mismatch file=%s", update.setup_name)
        _remove(target)
        return None

    _log.info("update downloaded version=%s", update.version)
    return target


def install_command(setup: Path, log_dir: Path | None = None) -> list[str]:
    """The silent Inno Setup command line, with its own log beside the app's.

    A silent update that failed is exactly the failure the user cannot see, so it
    writes a log into the folder the Settings button already opens (spec 8.5).
    """
    folder = log_dir if log_dir is not None else default_log_dir()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return [str(setup), *SILENT_FLAGS, f'/LOG={folder / f"update-{stamp}.log"}']


def install(
    setup: Path,
    log_dir: Path | None = None,
    release: Callable[[], None] = single_instance.release,
    reclaim: Callable[[], bool] = single_instance.claim,
    spawn: Callable[[list[str]], Any] | None = None,
) -> bool:
    """Drop the mutex and hand over to the installer. False means nothing started.

    The mutex goes first: Setup's `AppMutex` makes it refuse to run while the app
    holds the name, so the order here is the whole reason a silent update works.
    The caller closes the window straight after — the app must not be running when
    its own files are replaced.

    An installer that will not start puts the mutex back. The app stays open on
    this path, and an open app with no mutex is a second copy waiting to happen,
    both spending solves on the same accounts (spec 11.3).
    """
    start = spawn if spawn is not None else _detached
    command = install_command(setup, log_dir)

    release()
    try:
        start(command)
    except Exception as error:
        _log.error("update installer would not start error=%s", type(error).__name__)
        reclaim()
        return False

    _log.info("update installer started file=%s", setup.name)
    return True


def _checksum_for(session: Any, update: Update) -> str | None:
    try:
        response = session.get(update.checksums_url, timeout=TIMEOUT_SECONDS)
        if response.status_code != 200:
            _log.info("checksums refused http=%s", response.status_code)
            return None
        text = response.text
    except Exception as error:
        _log.info("checksums failed error=%s", type(error).__name__)
        return None

    wanted = expected_hash(text, update.setup_name)
    if wanted is None:
        _log.warning("checksums hold no line for %s", update.setup_name)
    return wanted


def _write_body(
    session: Any, url: str, target: Path, on_progress: Callable[[float], None] | None
) -> str:
    """Stream the body to disk, hashing as it goes. Returns the SHA-256.

    Hashed while writing rather than read back afterwards: the file is ~80 MB and
    a second full read buys nothing.
    """
    response = session.get(url, stream=True, timeout=TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise OSError(f"download http {response.status_code}")

    total = _length(response)
    digest = hashlib.sha256()
    done = 0

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
            if not chunk:
                continue
            handle.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if on_progress is not None:
                on_progress(min(1.0, done / total) if total else 0.0)

    return digest.hexdigest()


def _length(response: Any) -> int:
    """How many bytes are coming, or 0 when the server did not say."""
    try:
        return int(response.headers.get("content-length") or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def _asset(assets: Iterable[Any], wanted: Callable[[str], bool]) -> dict[str, Any] | None:
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        if isinstance(name, str) and wanted(name) and asset.get("browser_download_url"):
            return asset
    return None


def _parts(version: str) -> tuple[tuple[int, int, int], int] | None:
    """A version as something comparable, or None when it is not a version.

    The second number carries the pre-release rule: `1.2.0-rc1` sorts below
    `1.2.0`, so the committed `0.0.0-dev` placeholder is older than every real
    release and a candidate is replaced by the release it led to.
    """
    match = VERSION_SHAPE.match(version.strip())
    if match is None:
        return None
    major, minor, patch = (int(number) for number in match.group("numbers").split("."))
    return ((major, minor, patch), 0 if match.group("pre") else 1)


def _folder(folder: Path | None) -> Path:
    """Where the installer is downloaded to. Beside the logs, never in the app folder.

    The install folder is replaced by the very installer being written, and on a
    standard account it is not writable anyway (spec 11.3).

    Every earlier installer is deleted first. The file cannot be deleted after it
    is handed over — the app is gone and the installer is running from it — so
    the next download is what tidies up, and the folder never holds more than one
    ~80 MB file.
    """
    target = folder if folder is not None else default_log_dir().parent / "updates"
    target.mkdir(parents=True, exist_ok=True)
    for old in target.glob("*.exe"):
        _remove(old)
    return target


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        _log.info("could not delete the part-downloaded file")


def _detached(command: list[str]) -> Any:
    """Start Setup so it outlives the app that started it.

    DETACHED_PROCESS: the app is about to exit, and a child in its console group
    would be taken down with it mid-install.
    """
    creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0)
    return subprocess.Popen(command, close_fds=True, creationflags=creation_flags)


def _new_session() -> Any:
    # Imported here, not at module top: naming this module must not cost an
    # import of requests.
    import requests

    return requests.Session()
