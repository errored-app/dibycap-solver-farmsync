# Spend is counted from solves, never measured from the balance

The app shows what a run cost, live on the left panel and again on every history
row. The obvious way to get that figure is to remember `balance` when the run
started and subtract the `balance` the credit header just read. It is exact, it
needs no arithmetic, and it is wrong here.

**A dibycap key is not this app's alone.** The same key can be in use on another
machine, or in the browser, while a run is going. A measured drop charges this
run for every solve the key paid for anywhere, so a quiet night on one PC reads
as an expensive one because someone else was working. The figure would be
untraceable, too: nothing in the run's own counters would account for it.

The spend is therefore **counted**: `solved x price_per_1k / 1000`, from the
app's own `solved` counter and the last `price_per_1k` the credit header read.
One function in `credit.py`, called by the panel's spend block and by the
history rows and totals alike, so a row's money can never disagree with the
total above it.

## Consequences

- The figure is what **this app** spent, which is the question being asked. It
  is not a reconciliation of the dibycap account, and it is not offered as one.
- It is only ever as right as `price_per_1k`. A run that never read a balance
  has no price and shows no money at all rather than `$0.00`; a run billed at
  two different prices says the price changed instead of naming one
  ([#42](https://github.com/errored-app/dibycap-solver-farmsync/issues/42)).
- Attempts are free, so the count moves only on a solve. A round of 132 accounts
  that solved nothing costs nothing, and the panel says so.
- History rows store the price and the counts, never the money
  ([#43](https://github.com/errored-app/dibycap-solver-farmsync/issues/43)), so
  an old row can be re-read if this rule ever changes.

Settled in [#39](https://github.com/errored-app/dibycap-solver-farmsync/issues/39).
