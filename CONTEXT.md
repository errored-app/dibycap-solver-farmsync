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
- **Stopping** — no new accounts start; in-flight solves are finishing.

## Polite stop

Stopping that starts no new work but lets in-flight solves finish, because those
are already paid for. The opposite, dropping work at once, is not used.

## Close question

What the app asks before a run is dropped: *"A run is going. Stop it and close?"*
It is raised by the window's X and by Ctrl+W, and only while a run is on. An idle
app closes with no question.

## Terminal error

A solver error that is not about the **account** — for example an invalid key,
no balance, or a paused solve service. The first terminal error ends the run,
because every later account would fail the same way. Most terminal errors are
about the key; a paused service is not, and says so
([ADR 0002](docs/adr/0002-a-paused-solve-service-gets-its-own-code.md)).

## Attempt vs solve

An **attempt** is one account sent to the solver. A **solve** is an attempt that
actually cracked a captcha. Only solves are billed.

## Outcome

What one account came to: the account id, its **result**, and a detail. The
result is one of three — **joined** (got in, no captcha), **solved** (a captcha
was cracked), **failed** (could not be checked). A failed result carries the raw
dibycap code as its detail. Failures are routine, not an alarm.

## Speed

A user-facing percentage (25/50/75/100) of the key's reported `max_concurrent`.
It replaces a raw thread count.

## Credit

The work left in the dibycap key, counted in **solves**. Money is the secondary
form of the same thing. Attempts do not consume credit; only solves do.

## Low credit

Credit under a fixed threshold. It is a warning only — it never blocks a run.

## Out of credit

Credit at zero. A run will not start, and a running run stops.

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

## Update bar

The strip across the top of Home that names a found update and offers one
button. Non-blocking: it waits until the user presses it, and stays until then.

## Hand over

The last step of an update: the app drops its mutex, starts the silent
installer, and closes itself. Nothing before that point touches the installed
app, so a check, a download or a checksum that fails leaves the running version
exactly as it was.
