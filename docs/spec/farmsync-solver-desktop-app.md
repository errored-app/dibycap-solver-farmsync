# Spec: FarmsyncSolver Windows desktop app

**Status:** for approval
**Source:** [Map #1](https://github.com/errored-app/dibycap-solver-farmsync/issues/1) and its 15 resolved tickets
**Supersedes:** nothing. This is the first spec for this program.

This document is the whole plan. It is written to be implementable without reading
the issue tracker, but every section names the ticket that decided it, so any
"why" can be traced back to the argument that settled it.

---

## 1. What is being built

The console tool in `src/` becomes an installable Windows desktop application.

A non-technical person must be able to: run `Setup.exe`, open the app from the
Start menu, paste two keys, press one button, and watch it work. Nothing else.

**In scope:** the desktop app, its installer, and its auto-update path.
**Not in scope:** changing what the solver does. The captcha-solving behaviour is
the same behaviour the console tool has today.

### The rule that breaks every tie

> When developer flexibility fights end-user simplicity, end-user simplicity wins.

### 1.1 What the program does

`dibycap-solver-farmsync` polls **farmsync.cloud** for accounts that are enabled
and not currently running, sends each account's `.ROBLOSECURITY` cookie to the
**dibycap** solver API (`api.dibycap.com`), and reports the outcome as joined,
solved, or failed.

farmsync cannot tell which accounts still need a captcha cleared — its
`error: CAPTCHA` flag is never cleared when a captcha is solved. That stale flag
is the entire reason this program exists: it checks accounts and finds out.

Vocabulary for everything below is in [`CONTEXT.md`](../../CONTEXT.md).

### 1.2 Where it starts from

317 lines across 10 modules in `src/`, console-only, configuration in
`input/config.json`. **Every one of those 10 modules is moved, merged, or
deleted** (§9). Nothing survives unchanged.

---

## 2. Measured facts the design rests on

These were measured against the live account on 2026-08-17. Design decisions that
contradict them are wrong.

| Fact | Value | Decided in |
| --- | --- | --- |
| Devices on the account | 81 | #13 |
| Accounts visible via the bulk endpoint | 8,267 | #13 |
| Accounts that belong to a device | 4,352 | #13 |
| Accounts today's filter selects | 310–329 | #14 |
| Accounts the new eligibility rule selects | **132** | #14 |
| dibycap `max_concurrent` for this key | **65** (code hardcodes 15) | #12 |
| dibycap price | $1.50 per 1,000 **solves** | #12 |
| Per-account failure rate in normal operation | **28.6%** | #13 |
| Rounds completed in an 8-minute live run | **0** | #13 |
| Round time today | ~13 min, against a 60 s `round_delay` | #13 |
| Round time after this spec | **~72 s** | #13, #14 |
| Balance moved by 154 attempts, 0 solves | **$0.00** | #14 |
| Bulk accounts payload, uncompressed / gzipped | 103 MB / 11 MB in 11 s | #13 |

Three consequences worth stating outright:

1. **Attempts are free; only solves are billed.** The eligibility rule (§6) is a
   throughput fix, not a cost fix.
2. **A 28.6% failure rate is normal operation.** The UI presents failures as
   routine, never as an alarm.
3. **The program crashes on startup when stdout is not a live console** —
   `Output.banner()` prints a box-drawing character and Windows cp1252 raises
   `UnicodeEncodeError`. A windowed build has no console at all, so every
   `print()` in the engine is a crash. This drives §8 and §9.

---

## 3. Platform and shape

| Choice | Decision | Ticket |
| --- | --- | --- |
| OS | Windows only | charting |
| GUI framework | **NiceGUI in native desktop-window mode** — `ui.run(native=True)` via pywebview/EdgeChromium. No browser tab, no visible localhost URL. | charting, #2 |
| Packaging | **PyInstaller via `nicegui-pack`, `--onedir --windowed`** | #2, #11 |
| Installer | **Inno Setup**, per-user | #11 |
| Update feed | **Public GitHub Releases** on `errored-app/dibycap-solver-farmsync` | charting, #4, #5 |
| Runtime dependency | **Edge WebView2 Runtime** — bundled with the installer (§11) | #2, #11 |
| Port | Auto-scanned by NiceGUI (8000–8999). No fixed port, no collision handling. | #2 |
| Tray icon | **None.** The app is a window the user closes. | #9 |

**`nicegui-pack`, not bare `pyinstaller`.** Without NiceGUI's own `--add-data`
flag the frontend assets are missing and the UI ships blank.

**`--onedir`, not `--onefile`.** Onefile unpacks to temp on every launch (slower)
and draws more antivirus heuristics.

**`multiprocessing.freeze_support()` is mandatory** as the first statement in
`main.py`'s `if __name__ == '__main__':` block, or the frozen exe respawns itself
forever on Windows.

---

## 4. Screens

**Four screens: Setup, Home, Settings, History.** No separate About page. No
separate run screen. (#6, #44)

```
shortcut -> Setup (first run only) -> Home -> Start -> Home (running state)
                                       |
                                       +-> Settings (gear)
                                       +-> History (history icon)
```

They are written up as §4.1 Setup, §4.2 Home, §4.3 Settings, §4.5 History. §4.4
sits between the last two because it is a constraint rather than a screen, and
because half this repo cites it by number.

### 4.1 Setup

Shown **only** when keys are missing or unusable.

- Two boxes: the dibycap key and the farmsync token.
- One button: **Check and save**.
- Both keys are verified live before anything is saved:
  - dibycap — `POST https://api.dibycap.com/balance`, header `X-API-Key`. Cookie-free, so it **cannot spend solve credit**.
  - farmsync — `GET https://api.farmsync.cloud/api/devices/`, header `Authorization: Bearer <token>`.
- A bad key shows a plain-words error on **that box**, not a general failure.
- Success shows the credit figure inline — *"Key works — 5,662 captchas left"* — then goes to Home.

**Setup exists as its own screen rather than a greyed-out Home:** one task, one
screen, immediate feedback on a wrong key.

### 4.2 Home

The landing screen on every later open. One screen, two states.

**Always present:**

- **Header credit**, solves first and money second: `5,662 captchas left ($8.49)`. Turns **orange** under 1,000 solves. (§7)
- **Update bar** across the top when a newer release exists: a message plus **Update now**. Non-blocking, persists until acted on. Not a dialog — a dialog on open trains people to dismiss without reading.
- **Gear button** to Settings, and a **history icon** immediately left of it, tooltip *History* (§4.5). Two icons, no words: the top row is chrome, and a label up there would make the gear look like it lost one. (#44)
- **Background key re-check on open.** One cheap cookie-free call. On failure, a red line explains it and **Start is disabled** until it is fixed. This turns a mid-run mystery failure into a pre-run red line.

**One panel, two faces.** Home is a single tree that is built once and toggled,
never two screens (§4.4). Everything below is the same panel with parts shown or
hidden.

**Idle state:** a large **Start** button, and under it the **last-run block** in
the slot the headline and its message occupy during a run. The four counters, the
progress indicator and the spend block are hidden while Idle — they are
instruments for a run that is happening, and at rest they are the wreckage of
one. (#45)

```
Last run - Yesterday 23:14
2h 14m - 1,204 solved - $1.81
Stopped
                    All runs
```

- **Five facts, in that order**: when it started, how long it lasted, captchas solved, spent, how it ended. When-it-started leads because after a restart it is what makes the other four mean anything.
- **It reads the newest row of `history.json`** (§10.2), held in memory, re-read on app start and on each return to Idle. Never from the snapshot, which forgets everything on close, and never at the panel's 5 Hz.
- **The clock** reads `Today 23:14` / `Yesterday 23:14` / `19 Aug 23:14`. Not *"last night"* — it needs a definition and is wrong for anyone who runs during the day.
- **It drops any fact it cannot state.** A row with no `ended_at` has no duration and the middle line is `1,204 solved - $1.81`; a row whose price was never read loses the money the same way. A dash holds a table column's place, and reads as broken mid-sentence.
- **The ending** is the same wording table §4.5 uses, and carries **no colour**, for the reason in §4.5.
- **All runs** is a small text button to History. The icon at the top stays; someone reading *$1.81* and wondering about Tuesday should not have to go looking for it.
- **Before there is any history**, the slot reads *No runs yet.* A `history.json` from a newer version reads as no history and says **No last run to show.** instead, because telling a downgraded user *No runs yet.* is a lie about their own records. The explanation lives on the History screen.

**Running state — "the control room" (#8, prototype variant C):**

- A **fixed left panel** holds everything that is not a table row:
  - the single Start/Stop button
  - the status headline
  - the plain-words message
  - the progress indicator
  - the numbers: Round, Joined, Captchas solved, Could not check
  - the **spend block** below a rule: *Spent this run*, `$0.08`, over a working line reading *at $1.50 per 1,000* (§7.1)
  - the credit left and estimated solves
- **The rest of the window is one live table** of this round's accounts: status badge, username, detail, elapsed. **Newest first.**
- **Two switches above the table.** *"Show only the ones that failed."* — with ~38 failures in a 132-account round, that is the only filter needed. And *"Blur account names."*, which blurs every cell of the Account column past reading.
  - **Off at every launch, and never saved.** It is for the moment a screenshot is about to be taken, not a way to live.
  - **`filter: blur(6px)`**, one fixed value in `ui/theme.py`, the same in all five themes. At the table's ~14px type that is gone rather than smudged, and it stays gone in the monospace themes where the glyphs are wider. Note that CSS `blur()` takes a Gaussian **standard deviation**, so 6 here is far stronger than 6 in an image editor. (#40)
  - **No hover-to-reveal.** The switch is on because a screenshot or a screen share is in play, and a live share with the mouse tracking down the rows defeats it entirely. It is also a per-row hover state on a table repainting at 5 Hz, which is the fight §4.4 exists to avoid. To read a name, turn the switch off.
  - **It is not redaction, and the app does not pretend otherwise.** The username is still in the page's HTML, and blurred text in a known font is recoverable ([Hill et al., PoPETs 2016](https://petsymposium.org/popets/2016/popets-2016-0047.php)). The threat is a screenshot pasted into a chat, and that is the whole of it. This is why the switch says *Blur*, not *Hide*. (#41)
  - **Names only.** The credit header and the spend figures stay visible; money says nothing about who you are.
- **The scrolling console is gone.** Nothing is append-only text; every line is a row with a status.

**Progress indicators**, by run state:

| State | Indicator |
| --- | --- |
| Discovering | indeterminate spinner, *"Finding accounts…"* (~12 s, nothing to count) |
| Solving | determinate bar over accounts done / accounts selected — *"87 of 132"* |
| Resting | *"next round in Ns"* |

**Wording:** `Joined` / `Captcha solved` / `Could not check`. Failures are
**orange, not red** — they are expected, not an alarm. The raw dibycap code
(`INTERNAL_ERROR`, `CLASSIFICATION_ERROR`, `UPSTREAM_TIMEOUT`) appears only as the
row's detail, never as the headline.

**Devices are never shown.** No device list, no per-device rows, no 4,352-row
table. Totals only. (#13)

**No auto-start.** A stray double-click must never begin spending money. (#6)

### 4.3 Settings

Reached by the gear button, dismissed by a back arrow.

| Item | Notes |
| --- | --- |
| dibycap key | locked during a run |
| farmsync token | locked during a run |
| **Speed**: 25 / 50 / 75 / 100% | default 100. Locked during a run. |
| **Check for updates** | manual trigger, so a support conversation has something to point at |
| **Copy diagnostics** | §8 |
| **Open log folder** | §8 |
| **Forget my keys** | deletes the stored keys without needing a hidden `%APPDATA%` path. **Leaves the history alone** (§10.2) |
| About + version | absorbed here; no separate screen |

During a run, keys and Speed are locked with the note *"Stop the run to change
these."* The rest stays readable. **Settings stays reachable during a run on
purpose** — blocking it teaches the user the app is stuck.

### 4.4 The hard UI constraint

**Rebuilding the page on a timer swallows clicks.** In the prototype, refreshing
the whole tree five times a second made **Start** do nothing: the button element
was replaced between press and release. No error, no log line — the click just
vanished.

> **Rule: build interactive controls once. Only update their text and colour.
> Refresh only the non-interactive parts.**

This is a requirement, not a style preference. It shapes §9's engine seam. (#8)

### 4.5 History

Reached by the history icon on Home, dismissed by the back arrow Settings already
uses. One dense table of every run in `history.json` (§10.2), newest first, with a
totals strip above it. **No chart.** (#44)

**Totals**, two lines of small text, the second muted:

```
All time    $1,348.07 - 978,548 captchas solved - 161 runs
Last 7 days $88.59 - 73,822 captchas solved - 15 runs
```

All-time names its run count on purpose: `$1,348.07` alone is a number nobody can
place, and *161 runs* beside it makes it about eight dollars a run. Both lines
carry the same three facts in the same order, so the second reads as the first
narrowed rather than as a different sentence.

**Columns**, left to right: **Started - Lasted - Rounds - Joined - Solved - Could
not check - Spent - Ended.** Eight fit the 900x640 frame in all five themes,
monospace included. Started carries the year — 500 rows will cross one. The four
counts sit in the middle in the order the left panel lists them, so the two
screens read the same way round, and Spent sits beside Ended because those are the
two columns of the question the screen exists for.

**A run that never ended** shows a dash under Lasted, its real money under Spent —
solves that were billed were billed — and **App was closed** under Ended.

**What Ended says**, from the record's `ending` and `fault`
([ADR 0009](../adr/0009-the-history-names-its-own-ending.md)), as one table in
`ui/messages.py` keyed by the pair and never a sentence built in the screen:

| row | word |
| --- | --- |
| `stopped`, no fault | Stopped |
| `stopped` + `SERVICE_PAUSED` | Stopped while the service was down |
| `faulted` + `BAD_API_KEY` | Key was rejected |
| `faulted` + `NO_CREDIT` | Ran out of credit |
| `crashed` | Something went wrong |
| no `ended_at` | App was closed |

**The words carry the ending, not the colour.** Handheld flattens `--fs-warn`
close enough to the ink to vanish, so a colour here would cost a hint on one
theme and must never cost a fact. No badge, no icon, nothing built per theme
([ADR 0004](../adr/0004-one-screen-five-themes.md) holds with nothing added).

**Money** is two decimals, and a dash for a run whose `price_per_1k` was never
read. Those rows are counted by the run count and skipped by the money: a spend of
unknown is not a spend of nothing.

**Clear history** is a flat red text button on the title row, far right, disabled
when there is nothing to clear, behind a confirm:

> **Delete every run in your history?**
> That is 161 runs, and it cannot be undone. Your keys are not touched.
> *Cancel* - **Delete them**

The count goes in the question because *clear history* is abstract and *161 runs*
is not. The second sentence is there because **Forget my keys leaves the history
alone** (§4.3) and the reverse should be as plain. Afterwards the screen is the
empty state, with no toast to dismiss.

**Empty**, before the first run: the totals and the table are both gone and the
screen is two lines — ***No runs yet.*** / *Every run you start is written here,
with what it spent.*

**A file from a newer version** (§10.2) says so in one warn line under the title,
where the totals would be: *This history was written by a newer version of the
app.* The table and totals stay off, and **Clear history is not offered at all** —
this build has promised not to write that file, and a greyed button invites a
hunt for the way to enable it.

**This screen is drawn once per visit and never refreshed.** It has no timer, so
§4.4 costs it nothing.

---

## 5. Run lifecycle

### 5.1 States

**Idle → Discovering → Solving → Resting → Discovering …**, plus **Stopping**,
which returns to Idle. (#9)

Discovering and Solving are separate states because they have different progress
indicators.

The round is the unit of work: **round → 60 s rest → round.** Not a continuous
loop. The rest gives the user a visible idle state and a safe moment to stop.
`round_delay` becomes a code constant and — at ~72 s per round — is finally
reachable, which it is not today. (#13)

### 5.2 Start and Stop

- **Stop is polite.** No new accounts start; solves already in flight are allowed to finish, because an in-flight attempt may already be paid for. The button reads **Stopping…** and is disabled until the last one lands.
- **Stop during the rest is instant.** Nothing is in flight, so the rest is cut short.
- **Start after Stop is a fresh start.** Round counter back to 1, table cleared, every total reset. Carrying numbers over would make the screen lie about the current run.

### 5.3 Closing the window mid-run

A confirm dialog: *"A run is going. Stop it and close?"* with **Stop and close** /
**Keep running**. No tray icon.

### 5.4 Concurrency

Keep **worker threads**. Do not rewrite the solver to asyncio — `solver.solve` is
blocking `curl_cffi`, and the rewrite buys nothing the user can see.

Thread count is **derived, never stored**:

```
threads = floor(max_concurrent x speed_percent / 100), minimum 1
```

`max_concurrent` comes from `POST /balance` at runtime. For the observed 65 that
gives **16 / 32 / 48 / 65**. There is no raw thread number anywhere in the UI.

**If `/balance` is unreachable at run start, the run does not start.** There is no
fallback thread count: a run with no credit information can die halfway through,
and Home already re-checks the key on open, so a dead service is an already-known
state rather than a surprise. (#7)

### 5.5 What stops a run

**Stops the run:**

- dibycap key rejected
- **no credit left** (`estimated_solves == 0`)
- farmsync token rejected
- any solver **terminal** error — `invalid_api_key`, `insufficient_balance`, `key_disabled`, `key_expired`, `service_paused` — **on the first occurrence**, not after three. These are facts about the key, not the account: every later account fails identically and each one still burns time.
- an unexpected exception in the engine

**Does not stop the run:**

- farmsync unreachable, or no internet
- a single account failing

This **changes today's behaviour**, where `src/roblox.py` merely counts a terminal
error as a `fail` and carries on.

**Discovery failure is retried, not fatal.** With a single bulk call there is no
"skip that device" any more — it is all or nothing. Retry twice quietly, then show
one friendly line (*"Could not reach farmsync. Trying again in a minute."*) and
wait for the next round. (#13)

### 5.6 How errors are shown

A **plain-words headline in the left panel. Never a modal dialog.** For example:
*"Your dibycap key was refused. Open Settings and check it."*

A popup raised while the user is away is a wall; a headline can be read whenever
they come back. An engine bug shows *"Something went wrong and the run stopped."*
with a small **Details** link holding the raw text.

**Retries are hidden.** The existing 3-attempt retry is not surfaced. Showing
"trying again (2 of 3)" would make a normal run look broken.

### 5.7 Button rules

| State | Start/Stop | Settings (gear) | Keys + Speed |
| --- | --- | --- | --- |
| Idle | **Start** enabled | enabled | editable |
| Discovering / Solving / Resting | **Stop** enabled | enabled, read-only | locked |
| Stopping | **Stopping…**, disabled | enabled, read-only | locked |
| Key check failed on open | **Start** disabled, tooltip says why | enabled | editable |

---

## 6. Account eligibility

### 6.1 The rule

Send an account to the solver when **all** of these hold:

1. `account.enabled` is true
2. `account.running` is false
3. its device has `active_accounts > 0`
4. `account.error` is **not** `FACEVERIFICATION`, `MODERATED`, or `DEAD`
5. `account.dead_cookie` is false
6. `account.cookie` is non-empty

**It is a blocklist, not an allowlist.** `error == "CAPTCHA"` and an empty `error`
**both pass**. Neither is trusted; both get checked — because farmsync never
clears `CAPTCHA` when a captcha is solved, so the flag is stale by design. This is
why 110 of 154 attempts in the live run returned "joined" with no captcha present.

### 6.2 Device liveness is `active_accounts > 0`

Rejected alternatives:

- `client_running` — **not a boolean.** It is the string `"LDPlayer"` on all 81 devices.
- `is_enabled` — true on all 81, including a device silent for 163 hours.
- `last_updated` staleness — misses Devices 15, 49 and 78, which is 94 of the 177 wasted accounts.

### 6.3 Measured effect

| Filter | Accounts remaining |
| --- | --- |
| today (`enabled and not running`) | 310 |
| + skip devices with `active_accounts == 0` | 133 (−177) |
| + skip `FACEVERIFICATION` / `MODERATED` / `DEAD` | 133 (−0) |
| + skip `dead_cookie` | 132 (−1) |
| + skip empty cookie | 132 (−0) |
| **final** | **132 — 57% of the work removed** |

The device rule does all the work today. The error and cookie rules removed almost
nothing in this snapshot, but they are cheap and they are the correct guard for
states this snapshot happens not to contain.

Combined with reading `max_concurrent` instead of a hardcoded 15, a round goes
from ~12 minutes to about **72 seconds**.

### 6.4 Not configurable, and not reported

These are fixed rules in code. Only the keys and Speed are user-editable.

The UI does not report what it skipped. The user sees the count it is working on,
not the count it declined.

---

## 7. Credit

`POST /balance` is a **live data source**, not just a key check: 114 bytes,
0.3–0.6 s per call.

```json
{"success":true,"balance":8.4938,"estimated_solves":5662,
 "price_per_1k":1.5,"max_concurrent":65,"active":0,"type":"limited"}
```

| Field | Job |
| --- | --- |
| `estimated_solves` | the headline credit figure |
| `balance` | the money figure, shown small beside it |
| `price_per_1k` | derives the money figure, and prices the run's spend (below) |
| `max_concurrent` | drives the Speed control (§5.4) |
| `active` | **ignored** |
| `type` | **ignored** |

- **Display:** Home header, always visible, solves first: `5,662 captchas left ($8.49)`. Solves answers "can I run tonight?"; money is shown because the user pays in money and hiding it would read as a trick.
- **Refresh:** **every 10 s during a run**, plus once on the key check and once on Home open. The user watches the tank drain and tops up *before* it dies.
- **Low = under 1,000 solves.** The header turns orange. **Low never blocks a start** and raises no dialog. A fixed count, not a fraction of the run's starting point, because that start point changes every run and cannot be explained in one sentence. 1,000 was chosen against the evidence that solves are rare — 154 attempts consumed 0 — so it is real runway, not a permanent orange state.
- **Zero is terminal.** The run stops and will not start: *"You are out of credit. Top up to keep going."* Deliberately chosen against the fact that attempts are free — at zero the app would still *look* like it is working while fixing nothing, which is exactly the failure this user cannot diagnose.
- **`active` is ignored** and is **not** subtracted from the thread budget. It read 16 on the first probe and 0 on three later probes with this program not running — a blip, not a resident squatter. Subtracting a jumping number would make Speed mean a different thing minute to minute. If the key really is saturated elsewhere, the solver's own errors already surface it.
- **`type` is ignored.** Only `"limited"` has ever been observed. An unknown plan word in Settings would be a scary string with no action attached, and nothing branches on it.

### 7.1 What a run has spent

Counted, never measured: `solved x price_per_1k / 1000`, from the app's own
`solved` counter and the last price the credit header read. **Not** the drop in
`balance` — the same key can be in use on another machine, and a measured drop
would charge this run for someone else's work
([ADR 0007](../adr/0007-spend-is-counted-from-solves.md)). One function in
`credit.py`, called by Home's spend block, by History's rows and by its totals, so
a row's money can never disagree with the total above it. (#42)

**On the left panel** (§4.2) it is its own block under a rule, not a fifth
counter: *Spent this run*, `$0.08` to two decimals, over a working line reading
*at $1.50 per 1,000* that carries no solve count.

- **It settles at 1 Hz** while the counters keep 5. Money that flickers reads as money being lost.
- **The block is off the screen until a price has been read**, rather than showing a dash. A spend of unknown is not a spend of nothing.
- **Once two prices have been billed in one run**, the working line reads *the price changed mid-run* instead of naming one, because neither number is the rate that was paid.

**Zero-balance response shape is unobserved** (the test key has credit). Treat
`estimated_solves == 0` as out of credit rather than trusting `success` alone.

---

## 8. Logging and support

### 8.1 The file

| Aspect | Decision |
| --- | --- |
| Location | `%APPDATA%\FarmsyncSolver\logs\`, beside `config.json`. One folder holds everything the user owns. |
| Rotation | **One file per run**, named by local date and time. |
| Pruning | On startup: drop files older than 7 days, keep at most 20. |
| Format | Fixed-shape plain text: `2026-08-18 14:03:11  INFO  solve  account=8812 result=joined` |
| Tone | **Technical** — real error codes, real HTTP status, real exception names, plus the `Headline` name of whatever the user was reading on screen ([ADR 0005](../adr/0005-the-snapshot-carries-facts-not-sentences.md)). |
| Detail | One line per **account attempt** (id, result, error code), plus round start/end and every run-state change. |
| Verbosity switch | **None.** One format, always on. |

One file per run is chosen because the user reports trouble by *when* ("it broke
this morning"), and one file per run makes that a direct lookup. Per-account lines
are kept because the 28.6% failure rate is normal, so "which ones and why" is the
only question ever asked — round summaries discard the answer before it is asked.

### 8.2 Redaction is structural

**Cookies and keys are never passed to the logger.** Not masked — absent. Accounts
appear as their farmsync id only.

This is a hard rule on the engine, not a filter in the logging layer. Masking is a
bug waiting to happen, and the file is one the user is explicitly invited to paste
into a chat. If a secret is never handed to the logger, no formatting mistake can
leak it.

**The blur of §4.2 changes nothing here.** It is a screen treatment for a
screenshot, and the run log, the diagnostics bundle and `history.json` never held
a username to begin with. Nothing is obscured in any of them, because there is
nothing there to obscure.

### 8.3 Robustness

- **Logging is initialised first** — before config load, before any window — and a global excepthook writes uncaught exceptions to the file. Today a windowed build that dies at import time is a window that never appears and no evidence at all. CI's `--selftest` catches import breakage before release; this catches it on the user's machine.
- **A log failure never stops a run.** Folder locked, disk full: the app continues silently, with no log and no warning. A run must not die for a diagnostic, and "logging is off" is not something this user can act on.

### 8.4 Getting a log out

Two Settings buttons:

- **Copy diagnostics** — clipboard gets a short header (app version, Windows version, run state, key check result, credit left, Speed) plus the **last 200 log lines**. Roughly the last round; a whole file will not fit in a chat box.
- **Open log folder** — Explorer, newest file first, for when the whole file is wanted.

Paste-first beats attach-first: "press this button, then paste" is a shorter
instruction than "find the file, attach the file".

### 8.5 Neighbours

- The silent updater runs Inno Setup with `/LOG` pointed at the **same** folder. A failed silent update is precisely the failure the user cannot see.
- Uninstall treats logs as user data: they are deleted or kept under §11's single "Also delete your saved keys?" question. No second prompt.

---

## 9. Architecture

### 9.1 Package layout

```
main.py                        <- nicegui-pack entry: freeze_support(), open the native window
farmsync_solver/
  _version.py                  <- GENERATED at build time from the git tag
  config.py                    <- the ONLY file that knows config.json's shape + DPAPI
  credit.py                    <- what a /balance payload means: solves, money, low
  diagnostics.py               <- the Copy diagnostics report and Open log folder
  errors.py                    <- error types with stable codes; shared by engine, keys, updater
  history.py                   <- the ONLY file that knows history.json's shape
  keys.py                      <- check_api_key(key), check_farm_token(token)
  logging_setup.py             <- configures stdlib logging once, at process start
  looks.py                     <- the five themes: one block of values per theme, name included
  paths.py                     <- the ONLY file that knows %APPDATA%\FarmsyncSolver
  updater.py                   <- GitHub Releases check, download, checksum, run Setup.exe
  engine/
    __init__.py                <- re-exports Engine and the snapshot types
    run.py                     <- the Engine class: round-loop thread, workers, account queue
    snapshot.py                <- RunState, RunSnapshot, AccountRow
    farmsync.py                <- Farmsync: accounts(), devices()
    dibycap.py                 <- Dibycap: balance(), solve(cookie)
    eligibility.py             <- is_eligible(account, device) -> bool
  ui/
    app.py  setup.py  home.py  settings.py
    closing.py                 <- the close question: the window's X, Ctrl+W, the dialog
    history.py                 <- the History screen: totals, table, Clear history
    messages.py                <- the one error-code -> friendly-sentence table
    theme.py                   <- the CSS rules that wear a look, and the two calls that apply it
```

`history.py` is to `history.json` what `config.py` is to `config.json`: the one
reader and writer, going through `paths.py`, saving atomically through a temp
file. **The money is not in it.** Rows store the price and the counts, and
`credit.py` turns those into money for whoever asks (§7.1), so the file stays a
record of facts and the arithmetic stays in one place.

**The Engine writes history directly**, at run start, each round end and run end.
That is not a breach of §9.2's seam, which is about sentences crossing it: a
history row is facts, the same facts the snapshot already carries.

### 9.2 The engine/UI seam

`Engine` is the whole interface the UI gets. **Four members:**

```python
start(api_key: str, farm_token: str, speed_percent: int) -> None
stop() -> None
snapshot() -> RunSnapshot
take_new_rows() -> list[AccountRow]
```

- `start` takes **plain values, not a config object**, so the engine runs from a bare script with no config file. It resets every counter to zero, which gives §5.2's "Start after Stop resets everything" in one line.
- `stop` is the polite stop of §5.2.
- `snapshot` **always answers**, including when Idle.
- `take_new_rows` returns accounts finished since the last call.

**Snapshot + new rows, not an event stream.** The queue still exists inside the
engine; what changed is what crosses the seam. The UI sets labels from the
snapshot and appends rows — no event-kind dispatch, which is exactly the code
§4.4's build-once constraint makes fragile.

`RunSnapshot` is one **flat** frozen dataclass:

```
state, headline, detail, round_number, done, total,
joined, solved, failed, credit_left, estimated_solves,
seconds_left, seconds_waited
```

Every field is a fact and none is a sentence
([ADR 0005](../adr/0005-the-snapshot-carries-facts-not-sentences.md)): `headline`
is a `Headline` member or the `ErrorCode` a run ended on, the two `seconds` fields
are what the line under it counts, and `detail` is the raw text of that fault.

`AccountRow` is `username, outcome, detail, at`.

Flat, because the UI writes `label.text = s.joined`. Nested groups buy nothing and
add types to learn.

The snapshot types live in `engine/snapshot.py`, not `run.py`, so the UI never
imports the file full of threads.

**One `Engine` for the app's life**, not one per run. The Home timer runs
continuously; a per-run engine would force the UI to carry a fake empty snapshot
for the Idle case.

**Logging does not cross this seam.** Engine, UI and updater each call stdlib
`logging` directly. Routing log events through a deliberately narrow contract
would push a third concern across it. (§8.3)

### 9.3 Key checking sits outside the Engine

`keys.py` holds two plain functions that Setup and Home's re-check call directly.
Making them `Engine` methods would force the Setup screen to build an Engine just
to test a string.

`check_api_key` is `Dibycap(key).balance()` and **returns the whole payload, not a
boolean** — Setup, the Speed derivation and the header all read from the same call.

### 9.4 Clients

One class per service: `Dibycap` with `balance()` and `solve(cookie)`, `Farmsync`
with `accounts()` and `devices()`. Balance is not split off from solve — same
client, same key, and the key check and the credit read are the same call.

**No protocol and no fake adapter is defined.** One real implementation means the
seam is hypothetical. The rule stated instead:

> `engine/farmsync.py`, `engine/dibycap.py` and `updater.py` are the **only** files
> allowed to touch the network.

A seam gets added when a second adapter actually exists.

### 9.5 Discovery

Two calls per round, re-run every round, **never cached** (11 s inside a ~72 s
round is acceptable, and the payload goes stale quickly):

1. `GET /api/self/accounts` — every account in one request, ~11 s gzipped.
2. `GET /api/devices/` — ~1.2 s, needed for the `active_accounts > 0` liveness rule.

This replaces the 1 + 81 sequential per-device calls in
`Farmsync.solvable_accounts()`, which take 80 s.

**Gzip must be asserted, not assumed.** Without it the body is 103 MB and the call
does not finish in 90 s. `requests` and `curl_cffi` both send `Accept-Encoding:
gzip` by default, so this is a trap only for a hand-rolled client — assert it
anyway.

**Responses must never be assumed to be JSON.** A farmsync call with a missing
`Authorization` header returns a Cloudflare HTML challenge page, not JSON.

`solvable_accounts()`'s sort by `rejoining` is dead code — `rejoining` is false on
all 8,267 accounts. It goes.

### 9.6 Eligibility

`engine/eligibility.py`, one pure function `is_eligible(account, device) -> bool`
holding §6's blocklist. Discovery calls it, so callers receive only eligible
accounts. It is the single business rule in the app, it has an ADR behind it
([ADR 0001](../adr/0001-eligibility-is-a-blocklist.md)), and it tests with plain
dicts and no network.

The skip of the 3,915 device-less accounts is an **explicit, commented rule**
here — not an accident of the liveness filter.

### 9.7 Errors

`farmsync_solver/errors.py` sits at the package top, not under `engine/`, because
`keys.py` and `updater.py` raise from it too.

Typed errors carry a short **stable code**: `BAD_API_KEY`, `NO_CREDIT`,
`SERVICE_PAUSED`, `BAD_FARM_TOKEN`, `NO_INTERNET`, `UNKNOWN`. Today's
`SolverError` / `FarmsyncError` / `RobloxError` collapse into this —
`RobloxError` was never raised anywhere.

`SERVICE_PAUSED` was added after the first live round (#23): `/balance` answered
normally while every `/createTask` came back `service_paused`. It is terminal
like a bad key, but the key is not the problem, and `BAD_API_KEY`'s sentence
sends the user to re-paste a key that works. Growing the set from five codes to
six has an ADR behind it
([ADR 0002](../adr/0002-a-paused-solve-service-gets-its-own-code.md)), settled in
[#30](https://github.com/errored-app/dibycap-solver-farmsync/issues/30).

`key_disabled` and `key_expired` stay on `BAD_API_KEY`. They are real key faults,
so the sentence is imprecise about the fix, not wrong about the cause.

The terminal-error list in `src/roblox.py` becomes **codes, not substring matching
on `str(e)`**.

**All user-facing wording lives in one table in `ui/messages.py`.** The engine
holds no user copy. One exception, and only one: a theme's name sits on its
`Look` in `looks.py`, because a theme is one block and a name that can go missing
while the paint ships is a tile with a blank line under it
([ADR 0004](../adr/0004-one-screen-five-themes.md)).

### 9.8 What dies

| Module | Fate |
| --- | --- |
| `counter.py` + `thread_lock.py` (25 lines) | one `queue.Queue` of accounts |
| `output.py` | **deleted.** The engine never prints. |
| `util.py` | `config()` → `config.py`; `short()` moves to the UI as display formatting |
| `solver.py` | → `engine/dibycap.py`. Its module-level `API_KEY = Util.config()["api_key"]` is a second import-time read and goes with it. |
| `roblox.py` | folded into `engine/run.py` as the worker body |
| `main.py` | splits: entry point → root `main.py`, round loop → `Engine` |
| `farmsync.py` | → `engine/farmsync.py`, rewritten around the two bulk calls |

Net: all 10 of today's modules are moved, merged, or deleted.

---

## 10. Files the app writes

Two files in `%APPDATA%\FarmsyncSolver`, plus the log folder of §8. Neither is
ever written to the install folder, which is read-only for a standard user and is
replaced on every update.

### 10.1 `config.json` — configuration and secrets

**Location:** `%APPDATA%\FarmsyncSolver\config.json`, per Windows user. The
install folder is read-only for a standard user and is replaced on update, so
nothing writable lives there.

**Contents — exactly four fields:**

```json
{
  "version": 1,
  "api_key": "<DPAPI-encrypted>",
  "farm_token": "<DPAPI-encrypted>",
  "speed_percent": 100
}
```

`version` exists from day one so a later release can migrate the file shape.

**Secret storage: DPAPI, value-level.** Only the two key values are encrypted
(Windows DPAPI, current-user scope). The file itself stays readable JSON.
Credential Manager was rejected — more API surface, and the keys then live
somewhere the config file cannot describe. Plain text was rejected — these keys
spend real money.

**Removed from config entirely:**

- **`place_id` is dead code.** `grep -rn place_id src/` returns nothing. Deleted, not relocated.
- **`round_delay`** becomes a code constant.
- **`threads`** is no longer stored. It is derived (§5.4).

**One recovery path.** Config missing, unparseable, or DPAPI-undecryptable (file
copied to another PC or another Windows login) all collapse to the same behaviour:
clear the bad values, show Setup, ask for the keys. No special error screen.

**`%APPDATA%` survives uninstall**, so keys are never retyped — not across an
uninstall/reinstall, and not across any auto-update. An update must never send the
user back to Setup.

**No migration from `input/config.json`.** The installed app never looks for it.
It is a developer artifact, and importing it is a code path that exists for one
person, one time.

**`config.py` is the single central reader/writer:** loads the file once at
startup into a typed object, exposes the derived thread count, saves atomically
(temp file + replace). This removes `src/util.py`'s **import-time** `json.load`,
which today kills the process before any window can open.

### 10.2 `history.json` — what every run spent

Beside `config.json`, same folder, same atomic write. A versioned object, not a
bare array: an array has nowhere to hang a version, and without one there is no
telling an old file from a broken one. (#43)

```json
{
  "version": 1,
  "runs": [
    {
      "started_at": 1755690191.4,
      "ended_at": 1755693791.2,
      "ending": "stopped",
      "fault": "SERVICE_PAUSED",
      "rounds": 12,
      "joined": 840,
      "solved": 312,
      "failed": 402,
      "speed_percent": 100,
      "price_per_1k": 1.2
    }
  ]
}
```

- **No usernames, ever.** The file is safe to open in front of anyone, which is the whole reason the History screen can exist.
- **Times are epoch seconds**, like `AccountRow.at`; the screen formats them local. A stored local string is a timezone bug waiting for the first user who travels.
- **The money is not stored.** It is `solved x price_per_1k / 1000` on read (§7.1). Storing the answer beside the inputs invites a row that disagrees with itself.
- **`price_per_1k` is the last price read during the run**, because that is the rate the user was watching. A run that never read a balance has the field absent, shows a dash, and is skipped by the totals.
- **`speed_percent` stays** although nothing reads it today. History is the one kind of data that cannot be backfilled, and Speed is locked for the life of a run, so it is an honest per-run fact rather than a snapshot of a moving setting.
- **`ending` and `fault`**: [ADR 0009](../adr/0009-the-history-names-its-own-ending.md).
- **Written on run start, each round end, and run end** — not on a clean end only, because stop-and-close kills the process mid-run ([ADR 0008](../adr/0008-a-runs-record-is-written-when-it-starts.md)).
- **Last 500 runs**, pruned on startup the way logs are.

**How it fails — a run must not die for a record of itself, and must not grow a
UI element about one either.** None of this is ever shown on screen:

- **A corrupt file at startup** reads as an empty history, but the bad file is renamed to `history.json.corrupt` (one slot, overwritten) before anything writes. Unlike config, which the user can retype, spending records have no fallback, and a truncated write is not a reason to destroy 500 rows. Corrupt means anything that is not an object with an int `version` and a list `runs` — a bare array included.
- **One unreadable row does not condemn the file.** Rows are read one at a time; a row that is not an object, or whose required fields are missing or the wrong type, is dropped and logged, and the other 499 survive.
- **A write that fails** is swallowed and logged, never raised, and every later write still tries because the folder may unlock. The first failure logs at `warning` with the reason, later ones at `debug`, so a locked folder cannot put eighty identical lines in a four-hour run's log.
- **A file written by a newer version is read as empty and never written.** Not the corrupt path: it is left exactly where it is, and this build records nothing for the session. Downgrading is rare; truncating a newer build's rows to write one of ours is not a trade worth making. The visible consequence is §4.5's warn line.

**SQLite was rejected.** A dependency §11.2 keeps deliberately thin, bought
transactions nothing here needs.

**Forget my keys leaves `history.json` alone.** It is spending records, not
secrets, and deleting data the user did not ask about is its own bug. Uninstall
already covers it under §11's single question.

---

## 11. Build, release, install

### 11.1 A release is one git tag

`git tag v1.2.0` → push → GitHub Actions on `windows-latest`:

1. `uv sync --frozen` from a committed lock file.
2. Generate `farmsync_solver/_version.py` **from the tag** (`v1.2.0` → `1.2.0`).
3. `nicegui-pack --onedir --windowed --icon … main.py`. `--version-file` stamps the same number onto the `.exe` properties.
4. Run `dist/FarmsyncSolver/FarmsyncSolver.exe --selftest`. A non-zero exit fails the release.
5. Inno Setup (`iscc`) wraps `dist/` into `FarmsyncSolver-Setup-1.2.0.exe`.
6. Compute `SHA256SUMS.txt`.
7. Publish a GitHub Release with both assets, marked **pre-release** when the tag contains a `-`.

Nothing is ever built on a personal machine. The repo is public, so runner minutes
are free.

**The git tag is the single source of version truth.** `_version.py` is generated,
never committed with a real number (`0.0.0-dev` in a dev checkout). This makes the
"tagged 1.0.1, file still says 1.0.0, app offers itself an update forever" failure
structurally impossible.

**`--selftest` loads config, opens no window, and exits 0.** It catches the
import-time half of the two silent killers: a missing NiceGUI asset, and any stray
`print()` in a `--windowed` build where `sys.stdout` is `None` and raises
`AttributeError`. **It does not prove the window renders.** Only installing the
pre-release does.

**A pre-release channel.** `v1.2.0-rc1` is published as a GitHub pre-release, which
`releases/latest` skips, so no user's app auto-updates to it. It is the only way to
install a real `Setup.exe` before shipping it.

### 11.2 Dependencies

A **`uv` lock file**, pinning direct and indirect dependencies. `>=` ranges cannot
rebuild an old tag, and NiceGUI's own minor bumps have blanked native windows
before.

| Package | Status |
| --- | --- |
| Python | pin **3.12.x** |
| NiceGUI | pin **3.16.0** |
| pywebview | resolved via NiceGUI's `>=5.0.1,<7` (currently **6.2.1**) |
| PyInstaller | latest **6.x**, in the project venv, invoked via `nicegui-pack` |
| `requests` | stays (farmsync) |
| `curl_cffi` | stays (solver) |
| `colorama` | **dropped** — its only consumer is `src/output.py`, which is deleted |

### 11.3 Installer

| Decision | Reason |
| --- | --- |
| **Per-user install** to `%LOCALAPPDATA%\Programs\FarmsyncSolver` | No admin, no UAC — not at install and, crucially, **not on every auto-update**. Per-machine would put a UAC prompt in front of a silent update, which this user may well answer No to. |
| **Bundle the WebView2 Runtime bootstrapper** (~2 MB), installed only if missing | A missing runtime is a **blank white window with no error** — the worst failure mode for this user, and undetectable from inside a window that never loaded. |
| **Warn about the runtime download, and keep the bar moving** — a Ready-page note and a marquee during the step | The bootstrapper pulls ~200 MB from Microsoft before it installs anything, so on a slow line the window sits still for minutes and reads as dead (#32). Bundling the full runtime was tried and reverted: it grows Setup.exe from ~32 MB to ~233 MB, moving the same wait onto every download, including the ones that already have the runtime. |
| **Single instance** via an Inno Setup `AppMutex` the app creates at startup | Two copies would both open (ports are auto-picked) and **both spend solves on the same accounts**. The same mutex gives the silent installer a reliable "is it running" signal. |
| **Start-menu and desktop shortcuts** | The user opens the app from the Start menu. |
| **Uninstall asks "Also delete your saved keys?", defaulting to No** | Keys survive an ordinary uninstall. Default-No stops a silent uninstall eating them. Logs follow the same answer (§8.5). |

**No code-signing certificate.** The first install shows SmartScreen's blue
"Windows protected your PC" box. The click path — **More info → Run anyway** — is
documented for the user. Auto-updates after that are silent and never show it
again. Revisit only if real users balk.

Antivirus false positives on PyInstaller exes are a real, unresolved upstream
issue, worse on the 6.x line. `--onedir` is the mitigation taken; signing is not.

---

## 12. Auto-update

**A plain custom updater**, not a library. PyUpdater is archived (2022);
`pywinsparkle` has been abandoned since 2019; `tufup` is alive but is a TUF
cryptographic framework with key-management overhead disproportionate to a small
tool shipped from GitHub Releases.

**The chain:**

1. `GET /repos/errored-app/dibycap-solver-farmsync/releases/latest` (unauthenticated: 60 requests/hour, ample).
2. Compare to `_version.py`.
3. Find the asset by **pattern match** on `FarmsyncSolver-Setup-*.exe`, never by array order.
4. Download to a temp file.
5. Verify **SHA-256** against the `SHA256SUMS.txt` asset. GitHub computes no checksum itself.
6. The app **exits itself**, then launches:
   `Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /LOG="%APPDATA%\FarmsyncSolver\logs\..."`

`CLOSEAPPLICATIONS` / Restart Manager is a safety net, not the primary close
mechanism. `/NORESTART` guarantees no unprompted machine reboot.

**What the user sees:**

- **A silent background check on startup.** No UI at all when nothing is found.
- **When an update is found:** the non-blocking update bar on Home (§4.2), with **Update now** and a download progress bar. Never a technical prompt.
- **A manual Check for updates button** in Settings.
- **Never mid-run.** An update during a run would kill it.

**Failure handling: do nothing and keep running the current version.** No
internet, a half download, a checksum mismatch — all identical. The existing
install is never touched until the new installer is verified and launched.

---

## 13. Code standards

From the brief, and binding on the implementation:

- Type hints throughout.
- Clear naming; small focused functions.
- Classes only where they improve the architecture.
- `pathlib`, never string path joins.
- Context managers for files and DB handles.
- Centralised configuration — one reader (`config.py`), no import-time file reads anywhere.
- Structured error handling with the stable codes of §9.7.
- Pinned dependencies (§11.2).
- Comments only for non-obvious code.

UI standards: clear navigation, large buttons, descriptive labels, sensible
defaults, tooltips, confirmation dialogs, progress and loading indicators, success
notifications, friendly errors, disabled buttons when an action is unavailable.

---

## 14. Out of scope

- **The 3,915 accounts with no device.** The bulk endpoint exposes 8,267 accounts but only 4,352 belong to a device; the liveness rule drops the rest. A deliberate, commented skip. Solving them is a different effort with a different destination. (#13)
- **Changing what the solver does.** The captcha flow is unchanged.
- **macOS, Linux, and any non-Windows target.**
- **A tray icon or background service.** (#9)
- **A device or per-account browser.** (#13)
- **Code signing.** (#11 — revisit only if users balk.)
- **Treating the blur as redaction.** It is for a screenshot going into a chat, not for an adversary. The username stays in the page's HTML under any visual treatment, and reading it means already running code on the machine. (#39, #41)
- **Obscuring anything beyond the Account column.** The credit header and the spend stay visible; money says nothing about who you are. Widening the switch to "hide the interesting parts" makes it vaguer and harder to explain. (#39)
- **A spend-over-time chart on History.** With a few hundred rows it is decoration, and it is a design problem of its own. (#39)
- **A running total since the app opened.** History's all-time and 7-day totals answer the same question from a file that survives a restart. (#39)
- **Sorting, filtering or exporting the history.** Unanswerable until the screen exists and has been lived with. (#44)
- **Clearing the history from Forget my keys.** It would delete data the user did not ask about, and uninstall already covers it. (#39)
- **Any user-facing signal when a history write fails.** The bookkeeping is not the user's problem, and a toast about `history.json` during a run is noise about something they cannot fix. (#43)

---

## 15. Known gaps

Facts that are still unverified. None blocks implementation; each is a thing to
watch.

1. **Zero-balance response shape is unobserved.** Treat `estimated_solves == 0` as out of credit rather than trusting `success`. (#12)
2. **What a dead-device account costs when it *does* present a captcha is unmeasured.** Zero captchas were solved in the 8-minute sample, so the "attempts are free" finding has not been tested against a real solve on a dead device. (#14)
3. **`--selftest` does not prove the window renders.** Only installing the pre-release does. (#11)
4. **What the spend block does when `price_per_1k` has never been read** is untested beyond the rare first-round case. If it turns out to be more than that, the "show nothing until a price is read" rule needs revisiting. (#39, #42)
5. **Whether the blur switch wants to be a saved preference** is unknown. Revisit only if it turns out to be left on for hours at a time. (#39)
6. **The exact farmsync failure taxonomy is thin** — wrong token, expired token, 5xx and no internet largely collapse into one generic error. Treat farmsync failures generically. (#3)

---

## 16. Traceability

| § | Subject | Ticket |
| --- | --- | --- |
| 3 | NiceGUI native window, PyInstaller facts | [#2](https://github.com/errored-app/dibycap-solver-farmsync/issues/2) |
| 4.1, 7 | Key verification endpoints | [#3](https://github.com/errored-app/dibycap-solver-farmsync/issues/3), [#12](https://github.com/errored-app/dibycap-solver-farmsync/issues/12) |
| 12 | Auto-update pattern | [#4](https://github.com/errored-app/dibycap-solver-farmsync/issues/4) |
| 11 | Public repo as release host | [#5](https://github.com/errored-app/dibycap-solver-farmsync/issues/5) |
| 4 | Screen map | [#6](https://github.com/errored-app/dibycap-solver-farmsync/issues/6) |
| 10 | Config and secrets | [#7](https://github.com/errored-app/dibycap-solver-farmsync/issues/7) |
| 4.2, 4.4 | Run view (prototype variant C) | [#8](https://github.com/errored-app/dibycap-solver-farmsync/issues/8) |
| 5 | Run lifecycle and errors | [#9](https://github.com/errored-app/dibycap-solver-farmsync/issues/9) |
| 9 | Module layout and the engine seam | [#10](https://github.com/errored-app/dibycap-solver-farmsync/issues/10) |
| 11 | Build and release pipeline | [#11](https://github.com/errored-app/dibycap-solver-farmsync/issues/11) |
| 2, 5, 9.5 | Scale and round cost | [#13](https://github.com/errored-app/dibycap-solver-farmsync/issues/13) |
| 6 | Account eligibility | [#14](https://github.com/errored-app/dibycap-solver-farmsync/issues/14) |
| 7 | Credit and limits | [#15](https://github.com/errored-app/dibycap-solver-farmsync/issues/15) |
| 8 | Logging and support | [#16](https://github.com/errored-app/dibycap-solver-farmsync/issues/16) |
| 5.5, 9.7 | A paused solve service is not a bad key | [#30](https://github.com/errored-app/dibycap-solver-farmsync/issues/30) |
| 4, 8.2, 10.2, 14 | Hidden names and the spend record (map) | [#39](https://github.com/errored-app/dibycap-solver-farmsync/issues/39) |
| 4.2 | The blur on the Account column | [#40](https://github.com/errored-app/dibycap-solver-farmsync/issues/40), [#41](https://github.com/errored-app/dibycap-solver-farmsync/issues/41) |
| 4.2, 7.1 | The run's spend on the left panel | [#42](https://github.com/errored-app/dibycap-solver-farmsync/issues/42) |
| 10.2 | The history record, its ending, and how the file fails | [#43](https://github.com/errored-app/dibycap-solver-farmsync/issues/43) |
| 4.5 | The History screen | [#44](https://github.com/errored-app/dibycap-solver-farmsync/issues/44) |
| 4.2 | The last-run block on idle Home | [#45](https://github.com/errored-app/dibycap-solver-farmsync/issues/45) |

Prototype and research artifacts live on throwaway branches:
`prototype/run-view`, `research/nicegui-pyinstaller`, `research/key-validation`,
`research/auto-update`, `research/farmsync-api`.
