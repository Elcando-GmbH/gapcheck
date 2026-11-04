# Findings

Each rule in gapcheck exists because a data error was observed in production use. The
observations below come from daily runs over 324 US large caps, with prices from Yahoo
Finance via the open-source
`yfinance` library. They describe that feed on those days, not every feed on every day.

## F1 — A vendor's "previous close" can be an after-hours price (29 Oct 2026)

For FTNT, the convenience field `previousClose` returned 129.33. The actual regular-session
close of the previous day was 174.08. A gap computed against the convenience field would
have been about −1 % instead of about −27 %.

**Rule:** the previous close comes from the previous unadjusted daily candle. Convenience
fields are never used. An independent reference close is a cross-check that is noted, not a
replacement.

## F2 — Shortly after the open, the daily candle may still carry yesterday's open (30 Oct 2026)

In a run 11 minutes after the US open, 232 of 324 daily candles for the current day showed
an open identical to the previous day's open. 8 of the 19 gaps flagged in that run were
artefacts of this.

**Rule:** the opening price is the open of the first one-minute bar at or after 09:30 New
York. Without a minute bar, a daily open identical to the previous day's open is rejected
as stale.

## F3 — In the first minutes the opening price is preliminary (2 and 3 Nov 2026)

Runs 10 and 30 minutes after the open on two days obtained a one-minute bar for all 324
tickers each time. But the open of the first bar changed between the two runs:

| Change of the first-bar open between +10 and +30 min | 2 Nov | 3 Nov |
|---|---|---|
| Tickers with any change | 194 | 213 |
| > 0.5 % | 31 | 34 |
| Maximum | 1.43 % | 1.74 % |

At +10 minutes the daily open still disagreed with the minute-bar open by more than 0.5 % for
160 (2 Nov) and 193 (3 Nov) tickers. At +30 minutes it disagreed for 2 and 0.

Compared with the final daily open published after the session (same feed, unadjusted):

| | +10 min, 2 Nov | +10 min, 3 Nov | +30 min, 2 Nov | +30 min, 3 Nov |
|---|---|---|---|---|
| Equal to the final open | 80 | 62 | 259 | 271 |
| Median deviation | 0.11 % | 0.10 % | 0.00 % | 0.00 % |
| Deviation > 0.1 % | 171 | 161 | 34 | 19 |
| Deviation > 0.5 % | 34 | 38 | 6 | 3 |

The remaining deviations at +30 minutes have a different cause: 27 of 34 (2 Nov) and 19 of 19
(3 Nov) had not changed since +10 minutes, so waiting longer would not remove them. The first
minute bar and the daily open apparently measure different things for these tickers. A likely
explanation is the first trade against the official opening auction price; this has not been
verified.

Effect on the 5 % threshold: on 3 Nov the same four tickers crossed it at +10 minutes, at +30
minutes and with the final open, although one of them moved from −5.44 % at +10 to −5.05 % at
+30. On 2 Nov one ticker crossed it at +10 and +30 minutes with +5.14 % but not with the final
open (+4.95 %). Its minute-bar open had not changed between the runs, so this is the structural
difference described above, not a preliminary value.

**Consequence:** a gap computed in the first minutes is preliminary. From about 30 minutes after
the open the minute-bar open agrees with the final daily open for most tickers. The report records
the minutes after the open for every run. For historical tests, where only the daily open exists,
the remaining structural difference (mostly 0 %, in single cases 0.5 % to 2.3 %) is the gap between
live and historical data. Two days are a small sample; the comparison will be repeated.

## F4 — "Unadjusted" daily history is split-adjusted after the fact (4 Nov 2026)

Daily candles requested from the feed with `auto_adjust=False` are documented as unadjusted. For
four 2026 splits, the previous close delivered today is already divided by the split ratio:

| Split | Ratio | Previous close as delivered | Open on the split day | Gap as delivered | Gap after dividing again |
|---|---|---|---|---|---|
| Apr 2026 | 25:1 | 167.77 | 166.25 | −0.91 % | +2,377 % |
| Jun 2026 | 10:1 | 241.16 | 237.60 | −1.48 % | +885 % |
| Jul 2026 | 4:1 | 193.18 | 191.26 | −1.00 % | +296 % |
| Sep 2026 | 2:1 | 80.04 | 80.82 | +0.97 % | +102 % |

Dividing the previous close by the ratio, as a split rule naturally would, turns a normal day into
a false gap of +100 % to +2,400 %. Only dividends are left unadjusted in `Close`.

A database that appends new candles every night without rewriting old ones shows the opposite
error: the split stays in the stored series as a crash (−75 % on the 4:1 split above), which
distorts drawdowns and risk ratios until the series is reloaded.

Whether the previous close is already adjusted **on the morning of the split day** has not been
measured yet. It will be on the next large-cap split (20 Nov 2026).

**Rule:** `history_split_adjusted=True` (default) takes the previous close as delivered. Callers
with genuinely unadjusted history set it to `False`. If open and previous close still stand in the
ratio of a common split after this step, the check is blocked: either a split is not reported or
the flag does not match the data. If you cannot tell whether your history is adjusted, run a split
detector first, for example a comparison of the feed's previous close with an unadjusted close you
stored the night before.

## Status

| Finding | Rule in code | Tests |
|---|---|---|
| F1 | `gap.compute_gap` — candle close, reference as cross-check | `test_wrong_reference_is_noted_but_candle_wins` |
| F2 | `candles.select_open` — minute bar first, stale daily open rejected | `test_minute_bar_overrides_stale_daily_open`, `test_stale_daily_open_rejected_without_minute_bar` |
| F3 | `report.build_report` — minutes after open recorded per run, so early and later runs can be compared | `test_report_roundtrip` |
| F4 | `gap.compute_gap` — `history_split_adjusted`, block when prices still show a split ratio | `test_split_today_adjusted_history_is_default`, `test_unreported_split_blocks`, `test_wrong_history_flag_blocks_instead_of_false_gap` |
