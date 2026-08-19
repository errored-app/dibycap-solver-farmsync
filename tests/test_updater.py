"""§12: the auto-update chain.

Five steps, each testable on its own: ask GitHub, compare versions, find the
asset by pattern, download and checksum it, then run Setup and go.

Every failure in this file must read the same way — no internet, a half
download, a bad checksum — and must leave the running app alone.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from farmsync_solver import updater
from tests.fakes import FakeResponse, FakeSession

SETUP_URL = "https://example.test/FarmsyncSolver-Setup-1.2.0.exe"
SUMS_URL = "https://example.test/SHA256SUMS.txt"
BODY = b"pretend this is an installer" * 100


def release_payload(tag: str = "v1.2.0", **changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tag_name": tag,
        "assets": [
            {"name": "SHA256SUMS.txt", "browser_download_url": SUMS_URL},
            {"name": "FarmsyncSolver-1.2.0-win64.zip", "browser_download_url": "zip"},
            {"name": "FarmsyncSolver-Setup-1.2.0.exe", "browser_download_url": SETUP_URL},
        ],
    }
    payload.update(changes)
    return payload


def sums_text(body: bytes = BODY, name: str = "FarmsyncSolver-Setup-1.2.0.exe") -> str:
    digest = hashlib.sha256(body).hexdigest()
    return f"aaaa  FarmsyncSolver-1.2.0-win64.zip\n{digest}  {name}\n"


def download_session(body: bytes = BODY, sums: str | None = None) -> FakeSession:
    return FakeSession(
        {
            SUMS_URL: FakeResponse(text=sums if sums is not None else sums_text()),
            SETUP_URL: FakeResponse(content=body, headers={"content-length": str(len(body))}),
        }
    )


def an_update(version: str = "1.2.0") -> updater.Update:
    return updater.Update(
        version=version,
        setup_name=f"FarmsyncSolver-Setup-{version}.exe",
        setup_url=SETUP_URL,
        checksums_url=SUMS_URL,
    )


# --- step 2: compare to _version.py ----------------------------------------


@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("1.2.0", "1.1.9", True),
        ("1.2.0", "1.2.0", False),
        ("1.2.0", "1.3.0", False),
        ("1.10.0", "1.9.0", True),  # numbers, not text: 10 beats 9
        ("1.2.0", "0.0.0-dev", True),  # the committed placeholder is older than all
        ("1.2.0", "1.2.0-rc1", True),  # the release beats its own candidate
        ("1.2.0-rc1", "1.2.0", False),
        ("not a version", "1.0.0", False),  # unreadable never counts as newer
        ("1.2.0", "not a version", False),
    ],
)
def test_which_version_is_newer(latest: str, current: str, expected: bool) -> None:
    assert updater.is_newer(latest, current) is expected


# --- step 3: find the asset by pattern -------------------------------------


def test_an_update_is_found_and_carries_both_asset_links() -> None:
    found = updater.find_update(release_payload(), current_version="1.1.0")

    assert found == an_update()


def test_the_setup_asset_is_found_by_pattern_not_by_position() -> None:
    payload = release_payload()
    payload["assets"].reverse()

    found = updater.find_update(payload, current_version="1.1.0")

    assert found is not None
    assert found.setup_url == SETUP_URL


def test_the_current_version_finds_nothing() -> None:
    assert updater.find_update(release_payload(), current_version="1.2.0") is None


@pytest.mark.parametrize("dropped", ["FarmsyncSolver-Setup-1.2.0.exe", "SHA256SUMS.txt"])
def test_a_release_missing_either_asset_offers_nothing(dropped: str) -> None:
    payload = release_payload()
    payload["assets"] = [item for item in payload["assets"] if item["name"] != dropped]

    assert updater.find_update(payload, current_version="1.1.0") is None


@pytest.mark.parametrize("payload", [{}, {"tag_name": "v1.2.0"}, {"assets": []}, []])
def test_an_odd_payload_offers_nothing(payload: Any) -> None:
    assert updater.find_update(payload, current_version="1.1.0") is None


# --- step 1: ask GitHub ----------------------------------------------------


def test_the_check_asks_the_releases_latest_url() -> None:
    session = FakeSession(FakeResponse(payload=release_payload()))

    answer = updater.check(session=session, current_version="1.1.0")

    assert session.urls == [updater.RELEASE_URL]
    assert answer.update == an_update()
    assert answer.reached_github is True


def test_a_release_that_is_not_newer_reads_as_current() -> None:
    session = FakeSession(FakeResponse(payload=release_payload()))

    answer = updater.check(session=session, current_version="1.2.0")

    assert answer.update is None
    assert answer.is_current is True


@pytest.mark.parametrize(
    "refusal",
    [
        FakeResponse(status_code=404, payload={}),
        FakeResponse(status_code=200),  # a body that is not JSON
        FakeResponse(payload=["not an object"]),
        OSError("no internet"),
    ],
)
def test_every_failed_check_answers_the_same_nothing(refusal: Any) -> None:
    answer = updater.check(session=FakeSession(refusal), current_version="1.1.0")

    assert answer.update is None
    assert answer.is_current is False  # "we never asked" is not "you are current"


# --- step 5: the checksum --------------------------------------------------


def test_the_checksum_file_is_read_by_file_name() -> None:
    digest = hashlib.sha256(BODY).hexdigest()

    assert updater.expected_hash(sums_text(), "FarmsyncSolver-Setup-1.2.0.exe") == digest


@pytest.mark.parametrize("text", ["", "aaaa  someone-else.exe\n", "no-columns-here\n"])
def test_a_name_the_checksum_file_does_not_hold_has_no_hash(text: str) -> None:
    assert updater.expected_hash(text, "FarmsyncSolver-Setup-1.2.0.exe") is None


# --- step 4: the download --------------------------------------------------


def test_a_good_download_lands_in_the_folder_and_keeps_its_bytes(tmp_path: Path) -> None:
    path = updater.download(an_update(), folder=tmp_path, session=download_session())

    assert path is not None
    assert path.read_bytes() == BODY


def test_the_download_reports_how_far_it_got(tmp_path: Path) -> None:
    seen: list[float] = []

    updater.download(
        an_update(), folder=tmp_path, session=download_session(), on_progress=seen.append
    )

    assert seen and seen[-1] == pytest.approx(1.0)
    assert seen == sorted(seen)


def test_a_wrong_checksum_keeps_nothing(tmp_path: Path) -> None:
    session = download_session(sums=sums_text(body=b"a different build"))

    assert updater.download(an_update(), folder=tmp_path, session=session) is None
    assert list(tmp_path.iterdir()) == []


def test_a_download_that_never_arrives_keeps_nothing(tmp_path: Path) -> None:
    session = FakeSession(
        {SUMS_URL: FakeResponse(text=sums_text()), SETUP_URL: OSError("dropped")}
    )

    assert updater.download(an_update(), folder=tmp_path, session=session) is None
    assert list(tmp_path.iterdir()) == []


def test_a_checksum_file_that_will_not_load_stops_the_download(tmp_path: Path) -> None:
    session = FakeSession({SUMS_URL: OSError("dropped"), SETUP_URL: FakeResponse(content=BODY)})

    assert updater.download(an_update(), folder=tmp_path, session=session) is None
    assert session.urls == [SUMS_URL]  # nothing is fetched before it can be checked


def test_a_refused_download_keeps_nothing(tmp_path: Path) -> None:
    session = FakeSession(
        {SUMS_URL: FakeResponse(text=sums_text()), SETUP_URL: FakeResponse(status_code=500)}
    )

    assert updater.download(an_update(), folder=tmp_path, session=session) is None


# --- step 6: run Setup and go ----------------------------------------------


def test_the_installer_runs_silently_and_logs_beside_the_app_log(tmp_path: Path) -> None:
    setup = tmp_path / "Setup.exe"

    command = updater.install_command(setup, log_dir=tmp_path / "logs")

    assert command[0] == str(setup)
    for flag in updater.SILENT_FLAGS:
        assert flag in command
    log_flag = next(part for part in command if part.startswith("/LOG="))
    assert log_flag.endswith(".log")
    assert str(tmp_path / "logs") in log_flag


def test_the_app_drops_its_mutex_before_setup_starts(tmp_path: Path) -> None:
    setup = tmp_path / "Setup.exe"
    order: list[str] = []

    started = updater.install(
        setup,
        log_dir=tmp_path,
        release=lambda: order.append("mutex"),
        reclaim=lambda: order.append("reclaimed") is None,
        spawn=lambda command: order.append("setup"),
    )

    assert started is True
    assert order == ["mutex", "setup"]


def test_an_installer_that_will_not_start_gives_the_mutex_back(tmp_path: Path) -> None:
    order: list[str] = []

    def refuse(command: list[str]) -> None:
        raise OSError("nope")

    started = updater.install(
        tmp_path / "Setup.exe",
        log_dir=tmp_path,
        release=lambda: order.append("released"),
        reclaim=lambda: order.append("reclaimed") is None,
        spawn=refuse,
    )

    # The app stays open on this path, and an open app with no mutex is a second
    # copy waiting to happen.
    assert started is False
    assert order == ["released", "reclaimed"]


def test_a_second_download_clears_the_installer_the_first_one_left(tmp_path: Path) -> None:
    stale = tmp_path / "FarmsyncSolver-Setup-1.1.0.exe"
    stale.write_bytes(b"the last update")

    updater.download(an_update(), folder=tmp_path, session=download_session())

    assert stale.exists() is False
