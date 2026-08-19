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

**Three screens: Setup, Home, Settings.** No separate About page. No separate run
screen. (#6)

```
shortcut -> Setup (first run only) -> Home -> Start -> Home (running state)
```

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
- **Gear button** to Settings.
- **Background key re-check on open.** One cheap cookie-free call. On failure, a red line explains it and **Start is disabled** until it is fixed. This turns a mid-run mystery failure into a pre-run red line.

**Idle state:** a large **Start** button and the last-run summary.

**Running state — "the control room" (#8, prototype variant C):**

- A **fixed left panel** holds everything that is not a table row:
  - the single Start/Stop button
  - the status headline
  - the plain-words message
  - the progress indicator
  - the numbers: Round, Joined, Captchas solved, Could not check
  - the credit left and estimated solves
- **The rest of the window is one live table** of this round's accounts: status badge, username, detail, elapsed. **Newest first.**
- **One switch above the table: "Show only the ones that failed."** With ~38 failures in a 132-account round, this is the only filter needed.
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
| **Forget my keys** | deletes the stored keys without needing a hidden `%APPDATA%` path |
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
| `price_per_1k` | never shown; only used to derive the money figure |
| `max_concurrent` | drives the Speed control (§5.4) |
| `active` | **ignored** |
| `type` | **ignored** |

- **Display:** Home header, always visible, solves first: `5,662 captchas left ($8.49)`. Solves answers "can I run tonight?"; money is shown because the user pays in money and hiding it would read as a trick.
- **Refresh:** **every 10 s during a run**, plus once on the key check and once on Home open. The user watches the tank drain and tops up *before* it dies.
- **Low = under 1,000 solves.** The header turns orange. **Low never blocks a start** and raises no dialog. A fixed count, not a fraction of the run's starting point, because that start point changes every run and cannot be explained in one sentence. 1,000 was chosen against the evidence that solves are rare — 154 attempts consumed 0 — so it is real runway, not a permanent orange state.
- **Zero is terminal.** The run stops and will not start: *"You are out of credit. Top up to keep going."* Deliberately chosen against the fact that attempts are free — at zero the app would still *look* like it is working while fixing nothing, which is exactly the failure this user cannot diagnose.
- **`active` is ignored** and is **not** subtracted from the thread budget. It read 16 on the first probe and 0 on three later probes with this program not running — a blip, not a resident squatter. Subtracting a jumping number would make Speed mean a different thing minute to minute. If the key really is saturated elsewhere, the solver's own errors already surface it.
- **`type` is ignored.** Only `"limited"` has ever been observed. An unknown plan word in Settings would be a scary string with no action attached, and nothing branches on it.

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
| Tone | **Technical** — real error codes, real HTTP status, real exception names, plus the `ui/messages.py` code for anything the user saw on screen. |
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
  config.py                    <- the ONLY file that knows %APPDATA%\FarmsyncSolver\config.json + DPAPI
  credit.py                    <- what a /balance payload means: solves, money, low
  diagnostics.py               <- the Copy diagnostics report and Open log folder
  errors.py                    <- error types with stable codes; shared by engine, keys, updater
  keys.py                      <- check_api_key(key), check_farm_token(token)
  logging_setup.py             <- configures stdlib logging once, at process start
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
    close_guard.py             <- runs in the window process: the X asks before it closes
    messages.py                <- the one error-code -> friendly-sentence table
```

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
state, headline, message, round_number, done, total,
joined, solved, failed, credit_left, estimated_solves
```

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
holds no user copy.

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

## 10. Configuration and secrets

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

---

## 15. Known gaps

Facts that are still unverified. None blocks implementation; each is a thing to
watch.

1. **Zero-balance response shape is unobserved.** Treat `estimated_solves == 0` as out of credit rather than trusting `success`. (#12)
2. **What a dead-device account costs when it *does* present a captcha is unmeasured.** Zero captchas were solved in the 8-minute sample, so the "attempts are free" finding has not been tested against a real solve on a dead device. (#14)
3. **`--selftest` does not prove the window renders.** Only installing the pre-release does. (#11)
4. **The exact farmsync failure taxonomy is thin** — wrong token, expired token, 5xx and no internet largely collapse into one generic error. Treat farmsync failures generically. (#3)

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

Prototype and research artifacts live on throwaway branches:
`prototype/run-view`, `research/nicegui-pyinstaller`, `research/key-validation`,
`research/auto-update`, `research/farmsync-api`.
