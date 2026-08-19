"""What each look is made of, and the one stylesheet that wears it.

ADR 0004. Every theme is the same screen with different values: no theme adds,
moves or hides a control, so Home, Settings and Setup are built once and painted
five ways. That is the whole reason the set is cheap to keep.

Two halves, and the split matters:

- `RULES` is written once. It says *which* part of the app takes *which* value,
  and it names nothing but variables. It is added to the page a single time.
- `Look` is a bag of values. Picking a theme replaces the variables on `<body>`
  and nothing else, so a change is one attribute write and no rebuild.

Quasar's own brand variables are set in the same bag. Buttons, spinners, bars
and switches read `--q-primary` straight from Quasar's stylesheet, so handing it
our accent themes all of them without a single override.

Fonts are system stacks on purpose. The pixel and rounded faces in the mockups
are web fonts, and a desktop window that has to reach the network to look right
is a window that looks wrong whenever the network is down.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from nicegui import ui

from .. import config

_log = logging.getLogger(__name__)

MONO = "Consolas, 'Cascadia Mono', 'Courier New', monospace"
SANS = "'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"


@dataclass(frozen=True)
class Look:
    """One theme's values. The names are roles, never colours.

    `soft` colours are the tint a status sits on; the matching plain colour is
    the text on top of it. Both are needed because a light chip on a light panel
    and a light chip on a dark panel cannot be the same pair.
    """

    bg: str
    ink: str
    muted: str
    panel: str
    panel_edge: str
    chrome: str
    chrome_ink: str
    accent: str
    accent_ink: str
    ok: str
    ok_soft: str
    warn: str
    warn_soft: str
    info: str
    info_soft: str
    bad: str
    radius: str
    radius_small: str
    font: str
    shadow: str
    extra: dict[str, str] = field(default_factory=dict)

    def variables(self) -> str:
        """The values as one `style` attribute, ours and Quasar's together."""
        pairs = {
            "--fs-bg": self.bg,
            "--fs-ink": self.ink,
            "--fs-muted": self.muted,
            "--fs-panel": self.panel,
            "--fs-panel-edge": self.panel_edge,
            "--fs-chrome": self.chrome,
            "--fs-chrome-ink": self.chrome_ink,
            "--fs-accent": self.accent,
            "--fs-accent-ink": self.accent_ink,
            "--fs-ok": self.ok,
            "--fs-ok-soft": self.ok_soft,
            "--fs-warn": self.warn,
            "--fs-warn-soft": self.warn_soft,
            "--fs-info": self.info,
            "--fs-info-soft": self.info_soft,
            "--fs-bad": self.bad,
            "--fs-radius": self.radius,
            "--fs-radius-small": self.radius_small,
            "--fs-font": self.font,
            "--fs-shadow": self.shadow,
            # Quasar reads these itself. Handing it the accent themes every
            # button, spinner, progress bar and switch at once.
            "--q-primary": self.accent,
            "--q-positive": self.ok,
            "--q-negative": self.bad,
            "--q-warning": self.warn,
            **self.extra,
        }
        return "; ".join(f"{name}: {value}" for name, value in pairs.items())


LOOKS: dict[str, Look] = {
    # The default, and the layout every other theme borrows: soft white cards on
    # a cool grey field, one red accent, generous corners.
    "modern": Look(
        bg="#f2f3f6",
        ink="#16181d",
        muted="#6e7480",
        panel="#ffffff",
        panel_edge="#e5e7ec",
        chrome="#ffffff",
        chrome_ink="#16181d",
        accent="#d94141",
        accent_ink="#ffffff",
        ok="#1f7d51",
        ok_soft="#eef7f2",
        warn="#8a5c0d",
        warn_soft="#fdf1dd",
        info="#2f5bb0",
        info_soft="#eaf0fc",
        bad="#d94141",
        radius="16px",
        radius_small="10px",
        font=SANS,
        shadow="0 1px 2px rgba(22, 24, 29, 0.06), 0 8px 24px rgba(22, 24, 29, 0.05)",
    ),
    # Four shades of one green, square corners, hard shadow. A single hue means
    # the status colours cannot separate themselves, so they lean on the edge.
    "handheld": Look(
        bg="#8bac0f",
        ink="#0f380f",
        muted="#306230",
        panel="#9bbc0f",
        panel_edge="#0f380f",
        chrome="#0f380f",
        chrome_ink="#9bbc0f",
        accent="#0f380f",
        accent_ink="#9bbc0f",
        ok="#0f380f",
        ok_soft="#9bbc0f",
        warn="#0f380f",
        warn_soft="#8bac0f",
        info="#0f380f",
        info_soft="#9bbc0f",
        bad="#0f380f",
        radius="0px",
        radius_small="0px",
        font=MONO,
        shadow="4px 4px 0 #306230",
    ),
    # The same toy shapes with a real palette: warm paper, navy ink, a red bar
    # across the top and gold for anything that wants attention.
    "handheld-color": Look(
        bg="#f4e9cf",
        ink="#1d2b53",
        muted="#6a6250",
        panel="#fffdf5",
        panel_edge="#d8c79c",
        chrome="#b33a3a",
        chrome_ink="#fff6e0",
        accent="#b33a3a",
        accent_ink="#fff6e0",
        ok="#2f7d4f",
        ok_soft="#e4f2e6",
        warn="#8a5c0d",
        warn_soft="#fdf1dd",
        info="#2f5bb0",
        info_soft="#e8eefb",
        bad="#b33a3a",
        radius="12px",
        radius_small="8px",
        font=SANS,
        shadow="0 4px 0 #d8c79c",
    ),
    # Grey plastic chrome, sunken dark panels, purple keys. The one dark theme,
    # so every ink value is the light one and every panel is the dark one.
    "console": Look(
        bg="#2b2b30",
        ink="#e8e6df",
        muted="#918f89",
        panel="#1e1e21",
        panel_edge="#34343a",
        chrome="#cbc8bf",
        chrome_ink="#26262a",
        accent="#8f6bd8",
        accent_ink="#f3eeff",
        ok="#79d488",
        ok_soft="#1d2a20",
        warn="#edc063",
        warn_soft="#2a2417",
        info="#b99cec",
        info_soft="#241f2e",
        bad="#ff7a7a",
        radius="6px",
        radius_small="4px",
        font=MONO,
        shadow="0 3px 0 #4b2f80",
    ),
    # Sky behind navy cards with a gold edge. Also dark-panelled, and the only
    # theme whose accent is bright enough to need dark text on top of it.
    "adventure": Look(
        bg="#cfe9f8",
        ink="#ffffff",
        muted="#a9bde6",
        panel="#14306b",
        panel_edge="#f2c14e",
        chrome="#0b1c46",
        chrome_ink="#ffd45c",
        accent="#f0a92b",
        accent_ink="#0b1c46",
        ok="#86e57a",
        ok_soft="#123a2a",
        warn="#e8b52a",
        warn_soft="#3a2f10",
        info="#7fb6ec",
        info_soft="#122a52",
        bad="#ff8b8b",
        radius="18px",
        radius_small="12px",
        font=SANS,
        shadow="0 4px 0 rgba(8, 20, 50, 0.45)",
    ),
}

# Which part of the app takes which value. Added to the page once; it names no
# colour of its own, so a new theme never comes back here.
#
# `!important` is only on the text-colour helpers. They replace Tailwind classes
# that carried the same weight, and the utility they beat is still on the page.
RULES = """
body, .nicegui-content, .q-page, .q-layout {
  background: var(--fs-bg);
  color: var(--fs-ink);
  font-family: var(--fs-font);
}
.q-card, .q-table, .q-menu, .q-expansion-item__content {
  background: var(--fs-panel);
  color: var(--fs-ink);
  border-radius: var(--fs-radius);
}
.q-card { box-shadow: var(--fs-shadow); }
.q-table th { color: var(--fs-muted); }
.q-table td, .q-table tbody td { color: var(--fs-ink); }
.q-table th, .q-table td { border-color: var(--fs-panel-edge); }
.q-btn { border-radius: var(--fs-radius-small); }
.q-field__control { border-radius: var(--fs-radius-small); }
.q-field__native, .q-field__prefix, .q-field__suffix { color: var(--fs-ink); }
.q-field__label, .q-field__messages { color: var(--fs-muted); }
.q-toggle__label, .q-checkbox__label { color: var(--fs-ink); }
.q-expansion-item .q-item__label { color: var(--fs-ink); }
.q-tooltip { background: var(--fs-chrome); color: var(--fs-chrome-ink); }

/* The named colours the screens ask for, so no screen spells a colour out. */
.fs-ink { color: var(--fs-ink) !important; }
.fs-muted { color: var(--fs-muted) !important; }
.fs-ok { color: var(--fs-ok) !important; }
.fs-warn { color: var(--fs-warn) !important; }
.fs-bad { color: var(--fs-bad) !important; }

/* The bar across the top of Home: an offer, not a warning. */
.fs-notice {
  background: var(--fs-info-soft);
  color: var(--fs-ink);
  border-bottom: 1px solid var(--fs-panel-edge);
}

/* One theme tile in Settings. The preview inside it wears its own values. */
.fs-tile {
  border: 2px solid var(--fs-panel-edge);
  border-radius: var(--fs-radius-small);
  background: var(--fs-panel);
  cursor: pointer;
}
.fs-tile:hover { border-color: var(--fs-muted); }
.fs-tile-picked { border-color: var(--fs-accent); }
"""


def looks() -> dict[str, Look]:
    """Every theme the app ships, in the order Settings shows them."""
    return {key: LOOKS[key] for key in config.THEME_CHOICES}


def look(key: str) -> Look:
    """One theme's values. An unknown key falls back rather than raising.

    The file already refuses to load a theme nobody ships, so reaching here with
    a bad key means our own code passed one. It is worth a log line, and it is
    not worth a blank window.
    """
    found = LOOKS.get(key)
    if found is None:
        _log.warning("no such theme theme=%s; using %s", key, config.DEFAULT_THEME)
        return LOOKS[config.DEFAULT_THEME]
    return found


def install() -> None:
    """Put the rules on the page. Once per page, before anything is drawn."""
    ui.add_css(RULES)


def wear(key: str) -> None:
    """Paint the window in one theme, replacing whatever it wore before.

    `replace` rather than `add`: every theme sets the same variable names, and a
    merge would leave the old values behind for any name a later theme dropped.
    """
    ui.query("body").style(replace=look(key).variables())
