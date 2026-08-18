# farmsync API: measured facts

Probed live on 2026-08-17 against a real account. All numbers are aggregates.
**No cookies, tokens or account identifiers are recorded in this file.**

Docs: <https://farmsync.mintlify.app/api-reference/accounts/list-accounts>
(the user warns the published docs are old; everything below was verified by probe).

## Endpoints

| Endpoint | Method | Result |
|---|---|---|
| `/api/devices/` | GET | 200, JSON array of devices |
| `/api/devices/{device_id}/accounts` | GET | 200, accounts for one device (what the code uses today) |
| `/api/self/accounts` | GET | 200, **every** account in one call |
| `/api/devices/self/accounts` | GET | 500 |
| `/api/accounts`, `/api/self/devices/{id}/accounts` | GET | 404 |

The `self` segment in the published docs is real, but only on `/api/self/accounts`.
It is not a prefix that applies to the device routes.

### Auth and Cloudflare

| Case | HTTP | Body |
|---|---|---|
| good token | 200 | JSON |
| bad token | 401 | `{"message":"Invalid session"}` |
| **no** `Authorization` header | 403 | Cloudflare `Just a moment...` **HTML** |

Never assume a response parses as JSON. `src/farmsync.py` already sets
`trust_env = False`, which avoids proxy interference.

## The one-call endpoint is a big win, but only with gzip

`GET /api/self/accounts` on this account:

| | On the wire | Time |
|---|---|---|
| **without** `Accept-Encoding: gzip` | 65 MB and **still not finished at 90 s** | timed out |
| **with** gzip | **11.1 MB** | **11.4 s** |

Uncompressed body: **103 MB** for 8,267 accounts.

The bloat is one field: `data` averages ~13 KB per account and this app never
reads it. `cookie` is ~1 KB. Everything else is small.

Both `requests` and `curl_cffi` send `Accept-Encoding: gzip` by default, so this
is only a trap for hand-rolled clients - but it must be asserted, not assumed.

### Versus today's approach

`Farmsync.solvable_accounts()` fetches the device list, then loops **one request
per device**: 1 + 81 = **82 sequential requests**, each with a 30 s timeout and up
to 3 retries, before the first solve. One gzipped call to `/api/self/accounts`
replaces all of it in ~11 s.

## Account scale on this account

| Measure | Count |
|---|---|
| devices | 81 (all `is_enabled`, all `client_running`) |
| accounts returned by `/api/self/accounts` | **8,267** |
| accounts with a `device_id` | 4,352 |
| accounts with **no** device (unassigned) | 3,915 |
| sum of device `total_accounts` | 4,352 - matches the assigned count only |

So `/api/self/accounts` returns roughly **twice** what the per-device loop can
ever see. Whether the unassigned 3,915 should be solved at all is a product
question, not an API one.

## Account flags (all 8,267)

| Flag | True |
|---|---|
| `enabled` | 2,320 |
| `running` | 2,026 |
| `logged_in` | 7,624 |
| `dead_cookie` | **2,044** |
| `rejoining` | 0 |
| `unassigned` | 0 |

`rejoining` is 0 across the whole account, yet `solvable_accounts()` sorts by it -
that sort is currently a no-op.

`unassigned` is 0 even for the 3,915 accounts with no `device_id`, so that field
does **not** mean what its name suggests. Use `device_id` presence instead.

## The `error` field is the real eligibility signal

Undocumented but populated. Distribution across all 8,267 accounts:

| `error` | Count |
|---|---|
| `CAPTCHA` | 4,428 |
| `FACEVERIFICATION` | 1,947 |
| `MODERATED` | 73 |
| `DEAD` | 12 |
| empty | the rest |

`CAPTCHA` is the state this solver exists to clear. `FACEVERIFICATION`,
`MODERATED` and `DEAD` cannot be fixed by solving a captcha.

## Measured waste in today's filter

Today's filter is `enabled and not running`. On this account, right now:

| | Count |
|---|---|
| accounts selected for solving | **295** |
| of those, `error == "CAPTCHA"` | **179** |
| of those, no `error` at all | **116** |
| of those, `dead_cookie` | 1 |
| of those, on a device whose client is not running | **0** |
| of those, with no `device_id` | 0 |

### On the reported offline-device bug

The user reports that accounts on offline or shut-down devices still get solved,
wasting credit. The signal for it is `device.client_running`, which today's code
never reads - it only checks `device.is_enabled`.

**The bug is real in the code, but it could not be measured today: all 81 devices
were enabled and running at probe time, so the waste was 0.** The fix should still
land, and the numbers should be re-measured when devices are actually down.

One caveat found while checking: **3 of 81 devices had `last_updated` older than
5 minutes** while still reporting `client_running: true`. A device that stopped
reporting can keep a stale `true`, so freshness of `last_updated` is a better
liveness test than `client_running` alone.

## dibycap `/balance` for cross-reference

`POST https://api.dibycap.com/balance`, header `X-API-Key`, no body:

```json
{"success":true,"balance":8.4938,"estimated_solves":5662,
 "price_per_1k":1.5,"max_concurrent":65,"active":16,"type":"limited"}
```

At `price_per_1k = 1.5`, every 1,000 wasted attempts costs about **$1.50**.
`max_concurrent` is 65; `input/config.json` hardcodes `threads: 15`.
