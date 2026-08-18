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


# --- Speed and Forget my keys (spec 4.3, 5.4) --------------------------------


@pytest.fixture
def saved_pair(config_file: Path) -> Path:
    config.save(config.Config(api_key="abc", farm_token="xyz"), config_file)
    return config_file


def test_speed_offers_four_choices_and_defaults_to_the_top() -> None:
    assert config.SPEED_CHOICES == (25, 50, 75, 100)
    assert config.DEFAULT_SPEED_PERCENT == 100


def test_a_new_speed_is_saved_and_the_keys_stay(saved_pair: Path) -> None:
    saved = config.save_speed(50, saved_pair)

    assert saved.speed_percent == 50
    assert config.load(saved_pair).speed_percent == 50
    assert config.load(saved_pair).api_key == "abc"


def test_a_speed_outside_the_four_choices_is_refused(saved_pair: Path) -> None:
    with pytest.raises(ValueError):
        config.save_speed(60, saved_pair)

    assert config.load(saved_pair).speed_percent == 100


def test_the_thread_count_is_stored_nowhere(saved_pair: Path) -> None:
    config.save_speed(25, saved_pair)
    written = json.loads(saved_pair.read_text(encoding="utf-8"))

    assert set(written) == {"version", "api_key", "farm_token", "speed_percent"}


def test_forget_my_keys_clears_both_keys_and_keeps_the_speed(config_file: Path) -> None:
    config.save(config.Config(api_key="abc", farm_token="xyz", speed_percent=25), config_file)

    remaining = config.forget_keys(config_file)

    assert remaining.api_key == ""
    assert remaining.farm_token == ""
    assert remaining.speed_percent == 25
    assert remaining.is_ready is False
    assert config.load(config_file).is_ready is False


def test_forget_my_keys_leaves_no_readable_key_in_the_file(saved_pair: Path) -> None:
    config.forget_keys(saved_pair)
    text = saved_pair.read_text(encoding="utf-8")

    assert "abc" not in text
    assert "xyz" not in text


def test_forget_my_keys_on_a_missing_file_is_quiet(tmp_path: Path) -> None:
    assert config.forget_keys(tmp_path / "gone.json").is_ready is False
