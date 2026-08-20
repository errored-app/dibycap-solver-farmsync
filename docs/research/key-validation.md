# Key/token validation for the first-run screen

The desktop app's first-run screen needs to prove a dibycap solver API key and a
farmsync bearer token are valid before saving them, without spending solver
credit or relying on made-up endpoints. Neither `dibycap.com` nor
`farmsync.cloud` publishes developer/API documentation: dibycap has no
discoverable public web presence at all, and farmsync's public docs
(`docs.farmsync.cloud`) are end-user guides for a Roblox auto-farming tool with
no API/auth/error reference. Because of this, the only verifiable primary
source for both services is this repo's own client code
(`src/solver.py`, `src/roblox.py`, `src/farmsync.py`). The recommendations
below are the cheapest checks that follow directly from that code, with the
unverifiable parts (credit cost, exact status codes/bodies) flagged
explicitly rather than guessed.

## dibycap validity check

**CONFIRMED** — Only two endpoints exist anywhere in this codebase:
`POST /createTask` (body `{"cookie": ...}`, returns `{"task_id": ...}` or an
error) and `POST /getTask` (body `{"task_id": ...}`, polled until the task
leaves `pending`/`solving`/`processing`). Source: `src/solver.py` lines
21-35 (read directly during this research). Auth is header `X-API-Key: <key>`
(`src/solver.py` line 19-20). There is no third endpoint referenced anywhere
in `src/` — no `/balance`, `/status`, `/whoami`, `/account`, or similar.

**CONFIRMED** — `src/roblox.py` lines 9-11 define
`TERMINAL = ("moderated", "cookie dead", "cookie_dead", "invalid_api_key",
"insufficient_balance", "key_disabled", "key_expired", "service_paused",
"banned")`, matched case-insensitively as a substring of whatever exception
text comes out of `solver.solve()` (line 47: `any(p in detail.lower() for p
in TERMINAL)`). `solver.solve()` raises `SolverError` with text taken from
`resp.get("error") or resp.get("message")` (createTask, line 26) or
`result.get("error")` (getTask, line 34).

**UNVERIFIED** — Which endpoint actually emits `invalid_api_key`,
`insufficient_balance`, `key_disabled`, `key_expired`, or `service_paused`,
and in which field. Nothing in this repo shows a literal dibycap response
body, and there is no public API reference to confirm it. It is a reasonable
inference (not confirmed) that these are key/account-level failures and so
most plausibly come back from `createTask` — the first call made, before any
task exists — rather than from `getTask`, since `getTask` failures
(`success: false`) are more naturally about the *solve itself* (e.g. captcha
unsolvable, cookie dead/banned/moderated). But this is an assumption, not
something read from source or docs.

**No public documentation, dashboard, or status page exists.** Web searches
for `dibycap`, `dibycap.com`, `api.dibycap.com`, and "dibycap solver api"
returned no matching results — only unrelated companies with similar-sounding
names (Diviac, MobyCap, 1stDibs, etc.) and other captcha-solving services
(DeathByCaptcha, 2Captcha, CapSolver) that are not dibycap. This confirms
dibycap is a private/niche service with no discoverable public API reference,
account dashboard, or status page. **Do not invent** a `/balance` or
`/whoami` endpoint for it.

**Recommended cheapest check**: call `POST /createTask` with a syntactically
harmless but non-functional cookie value (e.g. an empty string, or a short
placeholder like `""` or `"invalid"` — matching the same
`{"cookie": ...}` shape used by `solver.solve()`) using the header the user
just typed, and inspect the response:

- If the JSON body's `error`/`message` field contains `invalid_api_key`,
  `key_disabled`, or `key_expired` (matched the same way `TERMINAL` does it,
  case-insensitive substring) → key is present in dibycap's system but
  rejected — **treat as "wrong or expired key"**.
- If it contains `insufficient_balance` → **the key itself is valid**
  (dibycap authenticated it) but has no credit — treat as a distinct
  "no balance" case, not a wrong-key case.
- If it contains `service_paused` → dibycap-side outage/maintenance, not a
  key problem.
- If a `task_id` comes back (or the error is unrelated to any TERMINAL
  string, e.g. a cookie-format complaint) → the key authenticated
  successfully; treat as **valid**. Do not proceed to poll `getTask` for
  validation purposes — the key check should stop at `createTask`.
- Any non-2xx HTTP status, timeout, or connection error → **"could not
  verify — check your internet connection"**, not a key-wrong message
  (can't distinguish key-wrong from network/service failure at the HTTP
  transport level without a documented status-code contract, which does not
  exist).

**Credit-cost caveat (UNVERIFIED, important):** whether calling `createTask`
with a garbage/empty cookie consumes solver credit merely by being called, or
only charges on a successful solve, **cannot be determined** from this
codebase or any public source — there is no dibycap documentation and no
billing/credit logic anywhere in `src/`. This is the single biggest open risk
in the "cheapest check" recommendation above: it is the *only* method
available given the confirmed two-endpoint API surface, but its cost is
unconfirmed. Recommend the app: (a) make this call at most once per key
entry (no retries on a plain rejection), (b) surface this risk to whoever
owns the dibycap account relationship before shipping, and (c) if dibycap
ever documents a free/cheap validation path, switch to it — this repo
currently gives no way to confirm one exists.

## farmsync validity check

**CONFIRMED** — Base URL `https://api.farmsync.cloud`, auth header
`Authorization: Bearer <token>` (`src/farmsync.py` lines 5, 15). The only
endpoints used anywhere in `src/` are `GET /api/devices/` (`_devices`, line
30) and `GET /api/devices/<id>/accounts` (`_accounts`, line 33). `GET
/api/devices/` is called first and unconditionally in normal operation
(`solvable_accounts`, line 36) — it does not depend on any device already
existing, so it is a reasonable, already-relied-upon read-only call to reuse
for validation.

**CONFIRMED** — On any non-2xx response, `r.raise_for_status()` raises
`requests.HTTPError` (line 22), which is a `requests.RequestException`
subclass, caught by the following `except requests.RequestException as e`
(line 24) and re-raised as `FarmsyncError(str(e))`. The exact HTTP status
code and JSON error body for a bad token are **not visible anywhere in this
repo** — the code only preserves whatever string `requests` generates for the
exception (typically of the form `"401 Client Error: Unauthorized for url:
..."` or similar, per the `requests` library's own `raise_for_status`
formatting), not a parsed status code or body.

**No public API documentation exists.** `docs.farmsync.cloud` is real and
live, but its full page index (fetched via `https://docs.farmsync.cloud/llms.txt`)
lists only end-user setup guides in Vietnamese and English (getting started,
license-key redemption, device allocation, automation scripts, LDPlayer/MuMu
emulator setup, "Roblox Web" setup) — there is no API reference, auth guide,
error-code table, or developer section. `farmsync.cloud` (the marketing site)
returned HTTP 403 to an unauthenticated fetch and was not otherwise
accessible. This confirms farmsync is a private/bespoke backend with no
public API contract; nothing about its exact status codes can be verified
beyond what the local code already shows.

**Recommended check**: call `GET /api/devices/` with the token the user just
typed (same call `solvable_accounts()` already makes in normal operation, so
it's known-safe and already exercised in production use). Because the exact
status code for "bad token" is unverified:

- Any 2xx response → **valid token**.
- Any non-2xx response (whatever code `requests.HTTPError`/`FarmsyncError`
  surfaces) → treat generically as **"token rejected — check it's correct
  and not expired"**, without claiming a specific status code the app can't
  actually confirm. Do **not** hardcode `401` vs `403` handling as if it were
  confirmed — REST convention suggests one of those, but this is
  **UNVERIFIED** and neither the code nor any doc confirms which.
- Timeout / connection error (no HTTP response at all, e.g.
  `requests.Timeout` or a DNS failure before any status line) → **"could not
  reach farmsync — check your internet connection"**, distinct from a token
  rejection.

## Failure cases per service

### dibycap

| Failure case | Can current code distinguish it today? | How |
|---|---|---|
| Wrong key | Partially | `TERMINAL` catches `invalid_api_key` as a substring of the exception text (`src/roblox.py:9-11,47`), but only if that literal string is what dibycap actually returns — unverified against real response bodies. |
| Expired key | Partially | Same mechanism, via the `key_expired` substring — same caveat as above. |
| No credit/balance | Partially | Same mechanism, via `insufficient_balance` — same caveat. This is the one failure case unique to dibycap (farmsync has no credit/balance concept anywhere in `src/farmsync.py`). |
| Service down (5xx/connection error) | No | `solver.solve()` does not check HTTP status at all — it calls `.json()` directly on the response (`src/solver.py` lines 22-23, 30-31) with no `raise_for_status()` or status check. A 5xx with a non-JSON or empty body would raise a generic JSON-decode exception, not something `TERMINAL` recognizes, and would fall through to generic retry/fail handling in `roblox.py`. |
| No internet (DNS/connection failure) | No | Same as above — any `curl_cffi` connection exception is just caught as a generic `Exception` in `roblox.py:45` and stringified; it is not distinguished from a key problem except by the fact that its text won't match any `TERMINAL` string, so it retries up to `MAX_ATTEMPTS` (3) before failing generically. |

Recommended UI messages: for the first-run check specifically (a single
`createTask` probe, not the retry loop in `roblox.py`), map `TERMINAL`
matches to specific messages ("Key rejected — check it's correct",
"Key rejected — expired", "Key valid but out of credit"), and map anything
else (non-2xx, JSON decode failure, connection/timeout exception) to a single
generic "Could not verify key — check your connection and try again."
message rather than guessing at which specific problem occurred.

### farmsync

| Failure case | Can current code distinguish it today? | How |
|---|---|---|
| Wrong token | Partially | Any non-2xx becomes `FarmsyncError(str(e))` (`src/farmsync.py` lines 22-24) — the app can detect "some error happened" but the code does not parse out a status code, so it can't confirm this was specifically a 401/403 vs. something else. |
| Expired token | No, not distinctly | Same generic `FarmsyncError` path — nothing in the code or any doc gives a distinct signal for "expired" vs. "wrong". |
| No credit/balance | N/A | No credit/balance concept exists anywhere in `src/farmsync.py` or `src/farmsync.py`'s usage — farmsync appears to be a device-management service, not a metered one. |
| Service down (5xx/connection error) | Partially | `requests.Timeout` is caught and retried up to 3 times before raising `FarmsyncError("timeout")` (`src/farmsync.py` lines 19-21) — this is the one case the code labels distinctly today. Other 5xx status codes fall into the same generic `raise_for_status()` → `FarmsyncError(str(e))` path as a wrong token, with no code-level way to tell them apart. |
| No internet (DNS/connection failure) | Partially | A DNS/connection failure before any HTTP response is also a `requests.RequestException`, caught the same way as a bad-status response (line 22-24) — string text differs (e.g. connection errors from `requests` mention "Failed to establish a new connection" rather than a status line) but the code does not parse or branch on this distinction today. |

Recommended UI messages: for the first-run check, treat the explicit
`"timeout"` case as "Could not reach farmsync — check your internet
connection", and treat every other `FarmsyncError` (any non-2xx status, or
a connection error whose text doesn't match a timeout) as one generic
"Token rejected or farmsync unreachable — check the token and your internet
connection" message, since the code cannot today reliably separate "your
token is wrong" from "farmsync is down" from "no internet" beyond the
timeout special case.

## Sources consulted

Local files read in full during this research:
- `src/solver.py`
- `src/farmsync.py`
- `src/roblox.py`
- `src/util.py`
- GitHub issue #3 (`gh issue view 3 --repo errored-app/dibycap-solver-farmsync`)

URLs fetched/searched during this research:
- Web search: `dibycap solver api "api.dibycap.com" documentation` — no relevant results.
- Web search: `"dibycap" captcha solver api key balance status endpoint` — no relevant results (returned unrelated captcha services: DeathByCaptcha, 2Captcha, SolveCaptcha, CapSolver).
- Web search: `dibycap.com` — no matching site found; only unrelated similarly-named companies (Diviac, MobyCap, 1stDibs, etc.).
- Web search: `"farmsync.cloud" api documentation` — surfaced `https://docs.farmsync.cloud/` and `https://farmsync.cloud/`.
- Web search: `"farmsync" roblox devices api bearer token` — no farmsync-specific API results; only unrelated Roblox Open Cloud docs.
- https://docs.farmsync.cloud/ — fetched; landing page for end-user docs ("auto farming tool").
- https://docs.farmsync.cloud/llms.txt — fetched; full page index, confirmed no API/auth/error documentation exists, only end-user setup guides (get-started, redeem-license, allocation-device, automation, autochange, setup guides for Web/LDPlayer/MuMu/Roblox Web, in Vietnamese and English).
- https://farmsync.cloud/ — fetched; returned HTTP 403, no content retrieved.
