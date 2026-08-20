# A run waits out a down solve service

> **Reverses:** spec §5.1, §5.4, §5.5 and §9.7, which describe a paused service as
> terminal and refuse to start a run while `/balance` is unreachable. Raised as
> [#56](https://github.com/errored-app/dibycap-solver-farmsync/issues/56).

A dibycap that is paused or unreachable ended the run
([ADR 0002](0002-a-paused-solve-service-gets-its-own-code.md) made
`SERVICE_PAUSED` terminal). It no longer does. A fault that is dibycap's own —
paused, unreachable, or answering something that is not JSON — now puts the run
into a new **Waiting** state, where it holds the accounts it already discovered,
lets the in-flight solves land, and knocks once a minute until the service comes
back. It waits without an end of its own; only the service answering, or Stop,
gets it out. `SERVICE_PAUSED` leaves `TERMINAL_ERROR_CODES`, which now holds only
the two faults the user must fix: `BAD_API_KEY` and `NO_CREDIT`.

> `TERMINAL_ERROR_CODES` is gone
> ([ADR 0006](0006-the-client-names-how-bad-a-failure-is.md)): the client names
> `Severity.ENDS_RUN` instead of a set naming the codes. The two faults, and
> everything else here, stand.

**`/balance` is not a health check for solving.** Measured twice against the live
key — on 2026-08-18 for ADR 0002, and again on 2026-08-18 while writing this —
`POST /balance` answered normally (5,662 solves, $8.49) at the same moment every
`POST /createTask` came back `service_paused`. So the probe is always the call
that failed: a refused solve is knocked on with a solve, a `/balance` that did
not answer is knocked on with a `/balance`. Probing the other call reports a
service that is up while the run still cannot take a step.

The probe is a real account held from the last discovery, not a made-up one.
While a run waits, **farmsync is not called at all**: the accounts call is ~103 MB
uncompressed, so a run that retried by looping whole rounds would hammer the one
endpoint we most want to leave alone. Two farmsync calls span an outage of any
length — one before it, one after. The round is then re-run in full, so nothing
the probe found is counted: a probe moves no counter, adds no row, and starts no
round.

## Considered options

**Keep ending the run, and let the user press Start again.** What we had. It
turns a service that fixes itself in ten minutes into a run that stops at 03:00
and does nothing until someone looks at the screen.

**Loop whole rounds and skip the solving.** The obvious retry, and the reason
this ADR exists: it re-discovers from farmsync every minute for the whole
outage, which is the exact traffic we are trying not to make.

**Probe with a junk cookie instead of a real account.** Cheaper to reason about —
no held account, works before anything is discovered — but it makes a throwaway
task on dibycap every minute, and a probe that succeeds is then wasted. A real
account is honest traffic. Its cost is that a run that has discovered nothing yet
has nothing to knock with, which is why a `/balance` fault probes `/balance`.

**Give up after a limit — thirty minutes, say.** Rejected: a limit is a rule the
user has to learn, and the state it lands in (Idle, with a stale message) is
worse than the state it leaves (Waiting, still trying, Stop right there).

## Consequences

- `Waiting` is a sixth run state. Every "is a run on?" test in the UI reads
  `state is not RunState.IDLE`, so Stop, the close question and the
  no-update-mid-run rule all cover it with no edit.
- `AppError` carries a `service` flag, set by the client that made the call.
  This is what keeps a *service* `UNKNOWN` (dibycap sent no JSON) apart from the
  `UNKNOWN` an engine bug becomes through `from_exception` — without matching on
  the text of an error, which spec 9.7 refuses. A bug still ends the run: it does
  not heal in a minute.

  > The flag is now `Severity.WAIT_IT_OUT` on the same `AppError`
  > ([ADR 0006](0006-the-client-names-how-bad-a-failure-is.md)). Still set by
  > the client that made the call, still never guessed from the text of an
  > error, and `from_exception` still leaves an engine bug where it cannot wait.
- `solve_account` now raises on a service fault instead of retrying it. Three
  attempts against a paused service are only a slower way to the same answer, and
  the same function is the probe.
- The engine has a second flag beside `_stopping`: `_pausing` means "take no new
  account, but the run is not over".
- A run can now start while dibycap is down. `/balance` refusing the run (spec
  5.4) still holds for a key fault and a zero balance — only service faults wait.
