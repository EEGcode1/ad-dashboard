# Gary vs source — discrepancy log

This file is the running record of cases where Gary's reported daily number
disagreed with this dashboard's parsed-from-source number. Automatically
appended to by `parsers/billing_cross_check.py` and by a weekly Cowork task.

**Rule:** any delta > 2% between Gary's digest email and this dashboard's
same-day total is a discrepancy and gets logged here.

---

## Known historical issues (pre-dashboard, carried over from Gary's W14 self-review)

| Date | Source | Issue | Impact |
|---|---|---|---|
| 2026-03-18 | SGI | Gary's parser read wrong xlsx tab | GGR inflated 1.70× |
| 2026-03-23 | SGI | Gary's parser read wrong xlsx tab | GGR inflated 1.96× |
| 2026-03-31 | All | Gary auto-sent a DRAFT with stale/wrong-dated data | day needs reconstruction from SGI |
| 2026-04-04 | All | Gary never generated the report | full day missing |
| W14 rollup  | — | 3/7 reports generated, 0/7 on time | reliability collapse |

---

## Live discrepancy log

_(new rows appended by audit tooling)_

| Logged UTC | Report date | Source | Gary € | Dashboard € | Δ % | Notes |
|---|---|---|---|---|---|---|
