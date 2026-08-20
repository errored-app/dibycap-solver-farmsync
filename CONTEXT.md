# Context

Glossary for FarmsyncSolver. Terms only — no implementation detail.

## Account

One Roblox account held in farmsync. Carries a `.ROBLOSECURITY` **cookie** and an
`error` flag. An account is **eligible** when it passes the blocklist rule (see
`docs/adr/`), and only eligible accounts are sent to the solver.

## Device

A farmsync machine that owns accounts. A device is **live** when
`active_accounts > 0`. Devices are never shown in the app; only totals are.

## Round

One full pass over the eligible accounts, followed by a fixed rest. The round is
the unit of work. Rounds repeat until the user stops the run.

## Run

Everything between the user pressing **Start** and the run ending. A run holds
many rounds. Its counters reset to zero on every new run.

## Run state

The named phase a run is in:

- **Idle** — no run. Start is available.
- **Discovering** — fetching accounts and devices from farmsync. Shows a spinner.
- **Solving** — sending eligible accounts to the solver. Shows a progress bar.
- **Resting** — the fixed pause between rounds.
- **Waiting** — the solve service is down and the run is sitting it out.
- **Stopping** — no new accounts start; in-flight solves are finishing.

## Polite stop

Stopping that starts no new work but lets in-flight solves finish, because those
are already paid for. The opposite, dropping work at once, is not used.

## Close question

What the app asks before a run is dropped: *"A run is going. Stop it and close?"*
It is raised by the window's X and by Ctrl+W, and only while a run is on. An idle
app closes with no question.

## Terminal error

A solver error nobody but the user can fix — an invalid key, or no balance. The
first terminal error ends the run, because every later account would fail the
same way and no amount of waiting changes that. A paused service used to be one
and is now a **service fault** instead
([ADR 0003](docs/adr/0003-a-run-waits-out-a-down-solve-service.md)).

## Severity

How bad a failure is, said as one of four words the moment the failing call is
made: *retry* (ordinary, try again), *account done* (this account is finished,
the run is not), *wait it out* (a **service fault**), *ends run* (a **terminal
error**). The client that made the call names it, and nothing downstream works
it out again from an error code.

## Service fault

A solver error that is about the **solve service** itself — it is paused, or it
did not answer. Neither the key nor the account is at fault, and it fixes itself
in time, so the run **waits** it out rather than ending. Farmsync errors are not
service faults: they have their own quiet retry inside a round.

## Waiting

The run state a **service fault** puts a run into. The run holds the accounts it
already discovered, stops taking new ones, and lets the in-flight solves land.
It then waits, without an end of its own, until the service answers or the user
presses Stop. Farmsync is not called at all while a run waits.

## Probe

The single call a **waiting** run makes each minute to ask whether the service is
back. It is always the same call that failed — a solve, or a credit read. A probe
is a knock on a door, never work: it moves no counter, adds no row, and starts no
round.

## Attempt vs solve

An **attempt** is one account sent to the solver. A **solve** is an attempt that
actually cracked a captcha. Only solves are billed.

## Outcome

What one account came to: the account id, its **result**, and a detail. The
result is one of three — **joined** (got in, no captcha), **solved** (a captcha
was cracked), **failed** (could not be checked). A failed result carries the raw
dibycap code as its detail. Failures are routine, not an alarm.

## Blurred names

The state the live table is in while the **blur switch** beside *Show only the
ones that failed* is on: every cell of the Account column is blurred past
reading. It is for a screenshot going into a chat, and it is not redaction — the
username is still in the page, and blurred text in a known font is recoverable by
anyone who wants it. The switch is off at every launch and is never saved, and it
hides names only: the credit header and the spend both stay as they are, because
money says nothing about who you are.

## Headline

The named line at the top of the left panel: which of a run's moments the user is
being told about — getting ready, finding accounts, waiting for the service,
stopped. It is a name the engine sets, never the English it reads as; the words
for one are picked when the panel is painted
([ADR 0005](docs/adr/0005-the-snapshot-carries-facts-not-sentences.md)). A run
that ended on a fault takes the fault's code as its headline.

## Speed

A user-facing percentage (25/50/75/100) of the key's reported `max_concurrent`.
It replaces a raw thread count.

## Theme

The look the user picked, held in the config and applied to the whole window.
There are five: Modern, Handheld, Handheld Color, Console and Adventure. A theme
is **paint only** — colour, corner, shadow and font family. It never adds, moves,
hides or renames a control, so every screen is built once and painted five ways
([ADR 0004](docs/adr/0004-one-screen-five-themes.md)). Unlike the keys and Speed,
a theme can be changed while a run is going.

In code a theme is a **Look**: one block holding that theme's name and every
value it paints with. `looks.LOOKS` is the five the app ships, in the order
Settings offers them, and it is the only list of them there is.

## Credit

The work left in the dibycap key, counted in **solves**. Money is the secondary
form of the same thing. Attempts do not consume credit; only solves do.

## Low credit

Credit under a fixed threshold. It is a warning only — it never blocks a run.

## Out of credit

Credit at zero. A run will not start, and a running run stops.

## Spend

What a run has cost, in money: solves x the key's `price_per_1k`, counted from
the app's own counter and never measured from the drop in **credit**
([ADR 0007](docs/adr/0007-spend-is-counted-from-solves.md)). Attempts are free,
so only a **solve** moves it. A run that has never read a price has no spend at
all, which is not the same as a spend of nothing.

## History

The record of every run this app has made, one row per run, kept in a file of its
own beside the config. It holds no usernames, so it is safe to open in front of
anyone. It is reached from Home as its own screen, and the newest row of it is
what Home's **last-run line** compresses.

## History record

One run's row in the **history**: when it started and ended, how many rounds, the
joined / solved / failed counts, the Speed it ran at, the price it was billed at,
and its **ending**. The money is not stored — it is worked out from the price and
the count whenever the row is read.

## Ending

How a run finished, as one of four words. Three are written by the app as the run
ends: **stopped** (the user pressed Stop), **faulted** (a **terminal error** ended
it) and **crashed** (an engine bug). The fourth, **interrupted**, cannot be
written and is read from a row with no end time: the app was closed or killed
while the run was still going. Beside the ending sits the **fault**, the error
code in force when the run ended, which is what separates three hours of waiting
that a user gave up on from three hours of work
([ADR 0009](docs/adr/0009-the-history-names-its-own-ending.md)).

## Last-run line

The block on the idle left panel naming the newest **history record**: when the
run started, how long it lasted, what it solved, what it **spent**, and its
**ending**. It stands in place of the live counters while no run is on, and it is
a compression of a history row, never a second account of one — it drops any fact
it cannot state rather than showing a dash.

## Run log

The record of one run, written to a file as the run happens. One run, one file.
It is written for the maintainer, not the user: it carries real error codes, not
the friendly words shown on screen. A run log never holds a cookie or a key —
those are never given to the logger at all.

## Diagnostics

The short bundle a user copies to the clipboard to report trouble: a header
describing the app and the current run, plus the tail of the current run log.
It is a copy for pasting, not the whole run log.

## Update

A published release newer than the version this app was built as. An update is
**found** by a check, **offered** by the update bar, and **handed over** to the
installer. Found is not offered mid-run, and offered is never a dialog.

While it is offered, an update is at one of four stages:

- **Ready** — waiting for the user to press the button.
- **Locked** — a run is going, so the button is dead and the bar says why.
- **Downloading** — fetching the installer and checking it.
- **Failed** — the download or the checksum did not come off. This version keeps
  running, and the button may be pressed again.

A check that nobody could make leaves the offer exactly as it was. The bar must
not vanish because the user went offline.

## Update bar

The strip across the top of Home that names a found update and offers one
button. Non-blocking: it waits until the user presses it, and stays until then.

## Hand over

The last step of an update: the app drops its mutex, starts the silent
installer, and closes itself. Nothing before that point touches the installed
app, so a check, a download or a checksum that fails leaves the running version
exactly as it was.
