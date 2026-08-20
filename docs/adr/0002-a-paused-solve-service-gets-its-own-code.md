# A paused solve service gets its own error code

Spec 9.7 fixed the stable code set at five codes. We add a sixth,
`SERVICE_PAUSED`, rather than fold dibycap's `service_paused` into
`BAD_API_KEY`. A paused solve service is a fact about dibycap, not about the
user's key, and the user has nothing to fix.

This was measured on 2026-08-18 against the live key: `POST /balance` answered
normally — 5,662 solves, $8.49 — at the same moment every `POST /createTask`
came back `service_paused`. The key was good throughout.

`SERVICE_PAUSED` stays **terminal** (spec 5.5): the first one ends the run,
because every later account is refused the same way.

> Superseded on this one point by
> [ADR 0003](0003-a-run-waits-out-a-down-solve-service.md): a paused service is
> no longer terminal — the run waits it out. The sixth code, and everything else
> here, stands.

## Considered options

**Fold it into `BAD_API_KEY`** (what #22 had to do, because it could not change
the spec). The sentence the user then reads is *"That dibycap key was not
accepted. Check it and paste it again."* It is wrong twice: the key was
accepted, and re-pasting fixes nothing. Spec 5.5 makes this the **only** line
shown when a run dies this way, so the cost is the whole failure story.

**Keep five codes and let `ui/messages.py` read the detail string too.**
Rejected: it puts a second source of wording next to the code, which spec 9.7
deliberately refused, and it re-introduces text matching on server free text
that spec 8.2 keeps out of the app.

**Give `key_disabled` and `key_expired` their own codes as well.** Not done
here. Both are real key faults, so `BAD_API_KEY`'s sentence is not *wrong* for
them — only imprecise about the fix (top up or renew, versus re-paste). Splitting
them is a separate call with no measurement behind it yet.

## Consequences

- The code set is six, not five. Spec 9.7 and `tests/test_errors.py` pin the
  list, so growing it again is a deliberate edit in both places.
- `farmsync_solver/engine/dibycap.py` maps the state by dibycap's stable code
  `service_paused` in `TERMINAL_CODES` — never by matching text in an exception.

  > `TERMINAL_CODES` is now `REFUSALS` and carries a severity beside each code
  > ([ADR 0006](0006-the-client-names-how-bad-a-failure-is.md)). Matching the
  > stable code rather than the text of an exception is unchanged.
- The user reads *"The captcha service is paused. Your key is fine. Try again
  later."* — no key fault named, no key action asked for.
- "Terminal error" no longer means "about the key". It means "ends the run
  because every later account fails the same way". `CONTEXT.md` says so.

Settled in [#30](https://github.com/errored-app/dibycap-solver-farmsync/issues/30).
