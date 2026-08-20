# A run's record is written when it starts, not when it ends

`history.json` holds one row per run. The natural place to write that row is at
the end, when every field is known. Doing it that way would lose a large share
of real runs.

**Stop-and-close kills the process mid-run.** `ui/closing.py` answers the close
question by starting the polite stop and then letting the window go; the run is
still `STOPPING` when the process ends. Closing the window is a normal way to
finish a night's work, not a crash, so a write-on-clean-end rule would silently
record nothing for it. Every real power cut, task-kill and hard reboot lands the
same way.

The row is therefore written **when the run starts**, and rewritten on each round
end and once more on the run's end, atomically through a temp file the way
`config.save` already does it. A row with no `ended_at` is not an error state: it
is the honest record of an app that died, and the history screen reads it as
**interrupted** and says *App was closed*
([#43](https://github.com/errored-app/dibycap-solver-farmsync/issues/43)).

## Considered options

**Write once, at the end.** Rejected above: the commonest ending is the one it
cannot record.

**Write once at the end, plus a flush on the close question.** Rejected: it makes
`ui/closing.py` know about the history file, and it still loses every ending that
does not go through a dialog.

**Write on every account.** Rejected: 132 accounts a round at a few rounds an
hour is a rewrite of the whole file every few seconds to buy a resolution nobody
reads. The round is already the unit the counters move in.

## Consequences

- The file is rewritten on run start, on every round end and on run end. A write
  that fails is swallowed and logged — the first at `warning`, later ones at
  `debug`, so a locked folder cannot fill a four-hour run's log with the same
  line.
- A run that is interrupted keeps the counts from its last completed round. The
  accounts solved in the round that was in flight are not in the file, and the
  money is short by that much. This is accepted: the alternative is writing far
  more often for a figure nobody is auditing to the cent.
- There is no "in progress" flag. A missing `ended_at` carries it, and only one
  row can ever have one, because a row is only ever written by a running app.

Settled in [#39](https://github.com/errored-app/dibycap-solver-farmsync/issues/39).
