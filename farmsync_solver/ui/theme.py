"""The rules that wear a theme, and the two calls that put them on the page.

ADR 0004. Every theme is the same screen with different values: no theme adds,
moves or hides a control, so Home, Settings and Setup are built once and painted
five ways. That is the whole reason the set is cheap to keep.

Two halves, and the split matters:

- `RULES` is written once, and lives here. It says *which* part of the app takes
  *which* value, and it names nothing but variables. It is added to the page a
  single time.
- The values are `farmsync_solver.looks`, one block per theme. Picking a theme
  replaces the variables on `<body>` and nothing else, so a change is one
  attribute write and no rebuild.

Quasar's own brand variables are set in the same bag. Buttons, spinners, bars
and switches read `--q-primary` straight from Quasar's stylesheet, so handing it
our accent themes all of them without a single override.
"""
from __future__ import annotations

from nicegui import ui

from .. import looks

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


def install() -> None:
    """Put the rules on the page. Once per page, before anything is drawn."""
    ui.add_css(RULES)


def wear(key: str) -> None:
    """Paint the window in one theme, replacing whatever it wore before.

    `replace` rather than `add`: every theme sets the same variable names, and a
    merge would leave the old values behind for any name a later theme dropped.
    """
    ui.query("body").style(replace=looks.look(key).variables())
