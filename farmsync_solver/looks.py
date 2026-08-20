"""The five themes: one block of values per theme, and nothing else.

ADR 0004. A theme is paint only, so what one is made of is a bag of values with
a name on it: no screen, no stylesheet and no nicegui. That is why this module
sits beside `config.py` rather than under `ui/` — `config` has to know which
themes ship in order to refuse one that does not, and it must not import a
window to find out.

`ui/theme.py` is the other half: the rules that say which part of the app takes
which value, and the two calls that put them on the page.

A sixth theme is one entry in `LOOKS` and nothing anywhere else. The name under
its tile and the small picture inside it both come off the `Look`.

Fonts are system stacks on purpose. The pixel and rounded faces in the mockups
are web fonts, and a desktop window that has to reach the network to look right
is a window that looks wrong whenever the network is down.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

MONO = "Consolas, 'Cascadia Mono', 'Courier New', monospace"
SANS = "'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"

# The one the app opens on, and the one an unreadable saved value falls back to.
DEFAULT = "modern"


@dataclass(frozen=True)
class Look:
    """One theme's values. The names are roles, never colours.

    `name` is the only field the user reads rather than sees. It is here so a
    theme is one block: the tile in Settings takes its label off the same object
    it takes its picture from, and neither can go missing without the other.

    `soft` colours are the tint a status sits on; the matching plain colour is
    the text on top of it. Both are needed because a light chip on a light panel
    and a light chip on a dark panel cannot be the same pair.
    """

    name: str
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
        name="Modern",
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
        name="Handheld",
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
        name="Handheld Color",
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
        name="Console",
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
        name="Adventure",
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


def look(key: str) -> Look:
    """One theme's values. An unknown key falls back rather than raising.

    The file already refuses to load a theme nobody ships, so reaching here with
    a bad key means our own code passed one. It is worth a log line, and it is
    not worth a blank window.
    """
    found = LOOKS.get(key)
    if found is None:
        _log.warning("no such theme theme=%s; using %s", key, DEFAULT)
        return LOOKS[DEFAULT]
    return found
