# One screen, five themes

The app now ships five **themes** — Modern, Handheld, Handheld Color, Console and
Adventure — and the user picks one in Settings. A theme is **paint only**: it
changes colour, corner, shadow and font family, and it changes nothing else. No
theme adds a control, moves one, hides one, or renames one. Home, Settings and
Setup are built once and painted five ways.

That rule is the whole decision. It is what keeps the set cheap: a sixth theme is
a block of values in `ui/theme.py` and a name in `ui/messages.py`, and it costs
nothing on any screen that already exists or on any screen written later.

The mechanism follows from the rule. `ui/theme.py` holds two halves that never
mix: `RULES`, written once, says which part of the app takes which value and
names no colour of its own; a `Look` is a bag of values. Picking a theme replaces
the CSS variables on `<body>` and touches nothing else, so a change is one
attribute write with no rebuild — spec 4.4's build-once rule, kept. Quasar's own
brand variables (`--q-primary` and friends) are set from the same bag, so
buttons, spinners, bars and switches are themed without a single override.

**A theme is not locked during a run.** Spec 5.7 locks the keys and Speed because
changing either mid-run would change what the run is doing. A theme changes
nothing the engine can see, so locking it would be a rule with no reason behind
it — and the run is exactly when a user is sat looking at the window.

**Fonts are system stacks.** The pixel and rounded faces the mockups were drawn
with are web fonts. A desktop window that has to reach the network to look right
is a window that looks wrong whenever the network is down, so Console and
Handheld wear Consolas rather than a face fetched from Google.

## Considered options

**One theme, the way it was.** Cheapest, and what we had. Rejected because the
user asked for the choice, and the rule above makes five nearly as cheap as one.

**Let each theme own its layout.** The two full skins that started this — a 90s
console with a hardware bar carrying RESET and EJECT, and an outdoor scene behind
bubble panels — were both drawn and both rejected here. Each would need its own
Home, its own Settings and its own Setup, and every screen written from then on
would have to be built five times. They live on in the design canvas as
`Console.dc.html` and `Adventure.dc.html`; what shipped are the token-only
versions of the same two ideas.

**Ship the theme as a stylesheet file per look.** Rejected: five files that each
repeat the same selectors is five places for them to drift apart, and the app
would have to serve static files it does not otherwise serve.

**Restyle by rewriting the Tailwind classes on each screen.** Rejected for the
same reason — it puts the decision back inside the screens, which is what having
one theme module is for.

## Consequences

- The config file holds a fifth field, `theme`. A value nobody ships reads as
  Modern rather than as a broken file, so a config written by a newer version
  downgrades safely.
- `forget_keys` keeps the theme. The keys are the user's secret; the theme is
  their taste, and only one of those is worth deleting.
- No screen spells a colour out any more. `text-gray-600` and its neighbours are
  gone, replaced by `fs-muted`, `fs-ink`, `fs-ok`, `fs-warn` and `fs-bad` —
  roles, resolved by whichever theme is on. A new screen that reaches for a
  Tailwind colour will look right on Modern and wrong on Console.
- The three badge colours on the live table (`BADGE_COLOUR`) are still Quasar's
  named green, blue and orange. They are solid chips with their own text colour,
  so they read on every panel; if a later theme breaks that, they become roles
  too.
- `settings.build` takes the theme beside the speed. Both are one stored value,
  read on the way in and written straight back to the file on a pick.
