# The history names its own ending

Every history row says how its run ended. `engine/run.py` already computes
something that looks like the answer — `_end_headline` returns a
`Headline | ErrorCode` — and serialising that union into the file would have
cost nothing to write.

It is not written. A row carries **two fields**: `ending`, one of three words the
writer names, and `fault`, the `ErrorCode` in force at the end, or nothing.

- `stopped` — the user pressed Stop.
- `faulted` — a terminal error ended it, named in `fault`.
- `crashed` — an engine bug, the `ErrorCode.UNKNOWN` case.
- `interrupted` is **derived on read** from a missing `ended_at`, and is the one
  ending nothing can write, because the process that would write it is the
  process that died ([ADR 0008](0008-a-runs-record-is-written-when-it-starts.md)).

Two fields rather than one, because "who ended this run" and "what was going
wrong" are two questions. A run that sat in `WAITING` for three hours and was
then stopped by hand is `stopped` + `SERVICE_PAUSED`, and it must not read like
three hours of real work ended by hand, which is `stopped` + nothing. Same
money, different rows.

## Considered options

**Serialise `Headline | ErrorCode`.** Rejected: `Headline` is a display enum with
eleven members, of which two can ever end a run. Putting it in a file makes the
history inherit every member added to it later, unasked, which is how a display
enum quietly becomes a storage format.

**An `Ending` enum mirroring `ErrorCode`.** Rejected: a second table kept in step
with `errors.ErrorCode` by hand, which is the exact duplication
[ADR 0006](0006-the-client-names-how-bad-a-failure-is.md) deleted. Splitting into
`ending` + `fault` needs no mirror — the code is stored as itself.

## Consequences

- `crashed` is written, not derived from `fault == UNKNOWN`, for ADR 0006's
  reason: the writer names it once and nothing downstream re-derives it from a
  code. `interrupted` is the single exception, and only because there is
  physically no writer at that moment.
- A new `ErrorCode` needs no history change. A new `Headline` needs none either.
- The words on screen come from one `(ending, fault)` table in `ui/messages.py`,
  read by the history rows and by Home's last-run block
  ([#45](https://github.com/errored-app/dibycap-solver-farmsync/issues/45)). Six
  rows today; an unlisted pair falls back to the plain word for its `ending`.
- Rows already on disk fix the vocabulary. Renaming a member later means a
  reader that understands both, which is why this is written down.

Settled in [#43](https://github.com/errored-app/dibycap-solver-farmsync/issues/43).
