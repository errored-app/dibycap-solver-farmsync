# Account eligibility is a blocklist, not an allowlist

farmsync never clears an account's `error: CAPTCHA` flag when the captcha is
actually solved, so that flag is stale by design and worthless as a *positive*
signal — which is the whole reason this program exists. We therefore select
accounts by excluding the states that cannot be solved at all, rather than by
requiring `error == "CAPTCHA"`: an account is sent to the solver when it is
`enabled`, not `running`, its device has `active_accounts > 0`, its `error` is not
`FACEVERIFICATION` / `MODERATED` / `DEAD`, `dead_cookie` is false, and the cookie
is non-empty. Accounts with `error == "CAPTCHA"` and accounts with no `error` at
all both pass; neither is trusted, both get checked.

## Considered options

**Device liveness** is `active_accounts > 0`. The obvious-looking alternatives all
fail against the live account:

- `client_running` is **not a boolean** — it is the string `"LDPlayer"` on all 81 devices, so every truthiness test on it passes.
- `is_enabled` is true on all 81 devices, including one that had been silent for 163 hours.
- `last_updated` staleness misses Devices 15, 49 and 78 — 94 of the 177 accounts that need skipping — because a dead device keeps sending a fresh heartbeat.

Requiring `error == "CAPTCHA"` as an allowlist was rejected for the reason above.

## Consequences

- The rule removes **57% of the work** (310 → 132 accounts on the live sample), which is what makes a round completable at all. The device rule does effectively all of it; the error and cookie checks removed 1 account, but they guard states this snapshot happens not to contain.
- **The payoff is throughput, not money.** Attempts are unbilled — 154 attempts moved the dibycap balance $0.00 — so this is not a cost saving. It halves round time.
- The liveness rule drops the 3,915 accounts that belong to no device. That is a deliberate, commented skip and is out of scope for this app.
- These rules are fixed in code and not user-configurable.

Settled in [#14](https://github.com/errored-app/dibycap-solver-farmsync/issues/14).
