"""ADR 0004: five looks, one screen, and a theme that never breaks the app."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from farmsync_solver import config
from farmsync_solver.ui import messages, theme

HEX = re.compile(r"#[0-9a-fA-F]{3,8}")


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    return tmp_path / "config.json"


@pytest.mark.parametrize("key", config.THEME_CHOICES)
def test_every_shipped_theme_has_a_look(key: str) -> None:
    assert key in theme.LOOKS


@pytest.mark.parametrize("key", config.THEME_CHOICES)
def test_every_shipped_theme_has_a_name(key: str) -> None:
    name = messages.theme_name(key)

    assert name and name != key


def test_no_look_ships_that_the_app_does_not_offer() -> None:
    """A look nobody can pick is dead paint, and it would never be seen again."""
    assert set(theme.LOOKS) == set(config.THEME_CHOICES)


def test_the_themes_are_offered_in_the_order_the_app_lists_them() -> None:
    assert list(theme.looks()) == list(config.THEME_CHOICES)


def test_the_default_theme_is_one_of_the_choices() -> None:
    assert config.DEFAULT_THEME in config.THEME_CHOICES


@pytest.mark.parametrize("key", config.THEME_CHOICES)
def test_a_look_hands_quasar_the_accent(key: str) -> None:
    """Buttons, spinners and bars are Quasar's, and this is how they get painted."""
    variables = theme.look(key).variables()

    assert f"--q-primary: {theme.look(key).accent}" in variables


def test_the_rules_name_no_colour_of_their_own() -> None:
    """A colour written into the rules would be the same in all five themes."""
    assert not HEX.search(theme.RULES)


@pytest.mark.parametrize("key", config.THEME_CHOICES)
def test_every_variable_the_rules_ask_for_is_one_a_theme_sets(key: str) -> None:
    """A misspelt variable paints nothing and says nothing. This is the alarm."""
    asked = set(re.findall(r"var\((--fs-[a-z-]+)\)", theme.RULES))
    given = {pair.split(":")[0].strip() for pair in theme.look(key).variables().split(";")}

    assert asked <= given


def test_an_unknown_theme_still_paints_the_window() -> None:
    assert theme.look("no-such-theme") is theme.LOOKS[config.DEFAULT_THEME]


# --- what the file does with it --------------------------------------------


def test_a_fresh_file_reads_as_the_default_theme(config_file: Path) -> None:
    assert config.load(config_file).theme == config.DEFAULT_THEME


def test_a_saved_theme_comes_back(config_file: Path) -> None:
    config.save_theme("console", config_file)

    assert config.load(config_file).theme == "console"


def test_saving_a_theme_keeps_the_keys_and_the_speed(config_file: Path) -> None:
    config.save(
        config.Config(api_key="abc", farm_token="xyz", speed_percent=25), config_file
    )

    config.save_theme("adventure", config_file)
    loaded = config.load(config_file)

    assert loaded.api_key == "abc"
    assert loaded.farm_token == "xyz"
    assert loaded.speed_percent == 25
    assert loaded.theme == "adventure"


def test_a_theme_nobody_ships_is_refused(config_file: Path) -> None:
    with pytest.raises(ValueError):
        config.save_theme("neon", config_file)


def test_a_theme_nobody_ships_reads_as_the_default(config_file: Path) -> None:
    """A file from a newer version must not leave the window with no look."""
    config_file.write_text(json.dumps({"theme": "neon"}), encoding="utf-8")

    assert config.load(config_file).theme == config.DEFAULT_THEME


def test_forget_my_keys_keeps_the_theme(config_file: Path) -> None:
    """The keys are the user's secret; the theme is their taste. Only one goes."""
    config.save(config.Config(api_key="abc", farm_token="xyz"), config_file)
    config.save_theme("handheld", config_file)

    remaining = config.forget_keys(config_file)

    assert remaining.api_key == ""
    assert remaining.theme == "handheld"
