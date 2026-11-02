# Findings

Each rule in gapcheck exists because a data error was observed in production use. The
observations below come from daily runs over a universe of 324 US large caps (the
holdings of a US large-cap ESG ETF), with prices from Yahoo Finance via the open-source
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

## F3 — The first minute bar is itself preliminary in the first minutes (2 Nov 2026)

Two runs on the same day, 10 and 30 minutes after the open, both obtained a minute bar for
all 324 tickers. But the open of the 09:30 bar changed between the runs for 194 tickers:

| Change of the 09:30 open between +10 and +30 min | Tickers |
|---|---|
| > 0.1 % | 145 |
| > 0.5 % | 31 |
| > 1.0 % | 5 |
| Maximum | 1.43 % |

At +10 minutes, the daily open and the minute-bar open disagreed by more than 0.5 % for
160 tickers, by up to 12.8 %. At +30 minutes they disagreed for 2 tickers. Both sources had
converged.

On that day the three flagged gaps (+12.7 %, +6.2 %, +5.1 %) were identical in both runs,
and no ticker crossed the 5 % threshold between runs. With open changes of up to 1.4 %, a
ticker near the threshold can cross it on another day.

**Consequence:** a gap flagged within the first minutes is preliminary. The report records
the minutes after the open for every run, so that an early signal can be confirmed by a
later run. Which delay is sufficient, and whether the converged value equals the official
exchange opening price, is still being measured.

## Status

| Finding | Rule in code | Tests |
|---|---|---|
| F1 | `gap.compute_gap` — candle close, reference as cross-check | `test_wrong_reference_is_noted_but_candle_wins` |
| F2 | `candles.select_open` — minute bar first, stale daily open rejected | `test_minute_bar_overrides_stale_daily_open`, `test_stale_daily_open_rejected_without_minute_bar` |
| F3 | `report.build_report` — minutes after open recorded per run | `test_report_roundtrip` |
