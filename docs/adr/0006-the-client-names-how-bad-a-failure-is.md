# The client names how bad a failure is

Reading one solve failure took four lookups across two modules:
`dibycap.TERMINAL_CODES` turned a dibycap string into an `ErrorCode`,
`dibycap.HOPELESS_CODES` was read a file away in `run.py`,
`errors.TERMINAL_ERROR_CODES` was a third, different set, and
`AppError(service=True)` was a flag the client set for `errors.is_waitable` to
read. Three of the four were code tables consulted after the fact, and adding a
seventh dibycap code meant finding all of them.

The client that made the failing call now names the severity once, when it
builds the `AppError`. `errors.Severity` holds the four names — `RETRY`,
`ACCOUNT_DONE`, `WAIT_IT_OUT`, `ENDS_RUN` — and nothing downstream consults a
code table.

**Nothing about the rules changed.** The six stable codes are the same six, a
paused service still waits (ADR 0003), the same four dibycap codes still get one
attempt, and the same two faults still end a run. This changes who decides, not
what was decided.

## Considered options

**Keep the tables, merge them into one module.** Rejected: it moves the lookups
without removing them, and the lookup is the problem. A `TERMINAL_ERROR_CODES`
in `errors.py` also cannot tell a *service* `UNKNOWN` from an engine-bug
`UNKNOWN`, which is why the `service` flag existed beside it in the first place.

**Severity on `ErrorCode` itself.** Rejected: the same code is two different
severities depending on who raised it. `UNKNOWN` is a wait when dibycap sends no
JSON and an ordinary retry when a captcha will not solve.

**A fourth name only for the worker.** Rejected: three names in `errors.py` and
a fourth rule in `run.py` is the split this ADR closes. `RETRY` is the default,
so every failure carries a severity whether or not its client thought about one.

## Consequences

- One place to add a seventh dibycap code: a row in `dibycap.REFUSALS`, which
  carries the `ErrorCode` and the severity together.
- `HOPELESS_CODES` is gone, so the worker no longer reads a table defined in
  another file. The retry rule in `solve_account` is one condition on the
  severity the client already named.
- `AppError.service` is gone; `is_waitable` reads `Severity.WAIT_IT_OUT`. The
  distinction ADR 0003 drew is unchanged — `from_exception` leaves an engine bug
  at `RETRY`, so a bug still never waits.
- A severity left unnamed is `RETRY`. That is the safe default for a failure
  nobody thought about, but it means a *forgotten* severity on a run-ending
  fault reads as an ordinary retry. `tests/test_errors.py` pins the two codes
  that must never escape unnamed.
- Every fake client in the tests names severities the way the real one does,
  because there is no longer a code table to fall back on.

Settled in [#36](https://github.com/errored-app/dibycap-solver-farmsync/issues/36).
