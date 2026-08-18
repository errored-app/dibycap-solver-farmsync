r"""§10: the one reader of %APPDATA%\FarmsyncSolver\config.json and DPAPI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from farmsync_solver import config


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    return tmp_path / "config.json"


def test_the_default_path_sits_under_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", r"C:\Users\Someone\AppData\Roaming")
    path = config.default_path()

    assert path.parent.name == "FarmsyncSolver"
    assert path.name == "config.json"
    assert path.parent.parent.name == "Roaming"


def test_a_missing_file_loads_as_empty(config_file: Path) -> None:
    loaded = config.load(config_file)

    assert loaded.api_key == ""
    assert loaded.farm_token == ""
    assert loaded.speed_percent == config.DEFAULT_SPEED_PERCENT
    assert loaded.is_ready is False


def test_saved_keys_come_back(config_file: Path) -> None:
    config.save(config.Config(api_key="abc", farm_token="xyz"), config_file)
    loaded = config.load(config_file)

    assert loaded.api_key == "abc"
    assert loaded.farm_token == "xyz"
    assert loaded.is_ready is True


def test_the_file_holds_exactly_the_four_fields(config_file: Path) -> None:
    config.save(config.Config(api_key="abc", farm_token="xyz"), config_file)
    written = json.loads(config_file.read_text(encoding="utf-8"))

    assert set(written) == {"version", "api_key", "farm_token", "speed_percent"}
    assert written["version"] == config.CONFIG_VERSION


def test_the_keys_are_not_written_in_plain_text(config_file: Path) -> None:
    config.save(config.Config(api_key="abc", farm_token="xyz"), config_file)
    text = config_file.read_text(encoding="utf-8")

    assert "abc" not in text
    assert "xyz" not in text


def test_saving_creates_the_folder(tmp_path: Path) -> None:
    path = tmp_path / "FarmsyncSolver" / "config.json"
    config.save(config.Config(api_key="abc", farm_token="xyz"), path)

    assert path.is_file()


def test_saving_leaves_no_temp_file_behind(config_file: Path) -> None:
    config.save(config.Config(api_key="abc", farm_token="xyz"), config_file)

    assert [p.name for p in config_file.parent.iterdir()] == ["config.json"]


def test_unparseable_json_loads_as_empty(config_file: Path) -> None:
    config_file.write_text("{not json", encoding="utf-8")

    assert config.load(config_file).is_ready is False


def test_a_value_that_will_not_decrypt_loads_as_empty(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "version": 1,
                "api_key": "bm90LWEtcmVhbC1ibG9i",
                "farm_token": "bm90LWEtcmVhbC1ibG9i",
                "speed_percent": 75,
            }
        ),
        encoding="utf-8",
    )
    loaded = config.load(config_file)

    assert loaded.api_key == ""
    assert loaded.farm_token == ""
    assert loaded.speed_percent == 75  # a good value survives a bad neighbour


def test_a_wrong_shape_loads_as_empty(config_file: Path) -> None:
    config_file.write_text(json.dumps(["a", "list"]), encoding="utf-8")

    assert config.load(config_file).is_ready is False


def test_a_silly_speed_falls_back_to_the_default(config_file: Path) -> None:
    config_file.write_text(
        json.dumps({"version": 1, "api_key": "", "farm_token": "", "speed_percent": 3}),
        encoding="utf-8",
    )

    assert config.load(config_file).speed_percent == config.DEFAULT_SPEED_PERCENT


@pytest.mark.parametrize(
    ("speed", "expected"),
    [(25, 16), (50, 32), (75, 48), (100, 65)],
)
def test_the_thread_count_is_derived_from_the_observed_65(speed: int, expected: int) -> None:
    assert config.Config(speed_percent=speed).threads(65) == expected


def test_the_thread_count_is_never_zero() -> None:
    assert config.Config(speed_percent=25).threads(1) == 1
