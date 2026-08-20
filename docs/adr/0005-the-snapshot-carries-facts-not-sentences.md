# The snapshot carries facts, not sentences

A headline used to be its own English text. `RunSnapshot.headline` held
`"Finding accounts…"`, the engine picked that string out of `ui/messages.py`, and
the log recovered the constant's name by scanning the module's `globals()` for
uppercase strings. Two things fell out of that, and both are gone now.

**The engine imported the UI package.** `engine/run.py` did `from ..ui import
messages` to get wording, so the arrow between the two halves of the app pointed
the wrong way. Nothing enforced it either: the rule was a comment in
`messages.py` asking the reader not to import `engine` back.

**A sentence is a poor identity.** `messages.name_of()` mapped a sentence back to
the constant that held it, for the log line spec 8.1 asks for. Its own comment
admitted the flaw — two constants with the same words would collide — and it
returned an empty string for the one case that mattered most, a run that ended on
a fault, because those sentences are built by `for_code()` and are not module
constants at all.

So the snapshot now carries a `Headline` member from `engine/snapshot.py`, and
`ui/messages.py` turns a member into a sentence when the panel is painted. A run
that ended on a fault carries the `ErrorCode` itself as its headline: the error
table already holds that sentence, and a code is exactly what the log wants.

The same rule took the rest of the wording with it. The engine used to build the
moving line under the headline — "87 of 132", "Next round in 9s", "Waiting for 2m
5s." — which is why the import survived every earlier attempt to cut it. The
snapshot now carries `seconds_left` and `seconds_waited` beside the counters it
already had, and `home.panel_of` writes all three lines. `engine/run.py` imports
nothing out of `ui`, and a test in `test_package_layout.py` imports it in a fresh
interpreter and fails if anything from `farmsync_solver.ui` shows up in
`sys.modules`.

## Considered options

**Leave it, and keep the one-way rule as a comment.** What we had. It survived
one review because it works; it fails the moment someone adds a headline that
reads like another, or wonders why the headless engine pulls in the UI package.

**Give `Headline` a member per error code as well.** It would drop the
`Headline | ErrorCode` union from the field. Rejected: it duplicates
`ErrorCode`'s six names, and then two enums have to be kept in step for no gain.
The headline of a failed run *is* the failure.

**Have the engine keep composing the sentences, and only name the headline.**
The issue's original shape. It deletes the `globals()` map but leaves the import,
because `run_progress`, `run_rest` and `run_waiting` still live in the UI. Half a
seam is not a seam.

**Have the UI compute the elapsed and remaining seconds itself from a timestamp
in the snapshot.** Fewer fields, but the wall clock in the UI thread and the
engine's `time.monotonic()` are not the same clock, and the countdown would drift
from the tick the engine actually waits on.

## Consequences

- `RunSnapshot.message` is now `RunSnapshot.detail`, and holds only the raw text
  of the fault that ended a run — the string behind spec 5.6's **Details** link.
  It is the one string in the snapshot the user reads as it stands. This is a
  rename against the field list in spec 9.2.
- `seconds_left` is `None` while a waiting run has a knock out, which is what
  puts "Checking now…" on screen instead of a countdown to nothing.
- The log's `shown` line records the member name (`NO_ACCOUNTS`) rather than the
  `messages.py` constant name (`RUN_NO_ACCOUNTS`), and a run that ended on a
  fault now records the code instead of an empty string.
- `ui/messages.py` imports `engine.snapshot`, so the seam's one-way arrow now
  runs from the UI into the engine, the direction every other UI module already
  used. `OUTCOME_WORD` stopped being keyed by `Result.value` and is keyed by
  `Result`, which is what that key was working around.
- The cost of that arrow: importing `ui/messages.py` now runs
  `engine/__init__.py`, which imports `run.py` and the two clients under it. It
  buys nothing back, because every module that imports `messages` is part of a
  window that builds an `Engine` anyway — but the module is no longer the cheap
  leaf it was, and a headless caller that wants only the sentences pays for the
  threads it will not start.
