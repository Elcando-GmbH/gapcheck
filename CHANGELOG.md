# Changelog

## 0.1.2 — 2026-11-03

- Linter version pinned (`ruff==0.17.3`), so a new ruff release cannot break CI unnoticed
- docs/FINDINGS.md: universe described as 324 US large caps only

## 0.1.1 — 2026-11-02

- `daily_open`: the daily open as delivered is kept in `TickerQuotes`, `GapResult` and the report
- One-minute bars more than `max_delay_minutes` (default 5) after 09:30 are ignored; the daily-open rules apply
- Threshold comparison tolerates floating-point rounding, so an exact threshold gap triggers
- Version defined once, in `gapcheck/__init__.py`
- README: where the input frames come from, with an optional yfinance example

## 0.1.0 — 2026-11-02

First public release.

- Opening price from the first one-minute bar at or after 09:30 New York; stale daily open rejected
- Previous close from the unadjusted daily candle; optional reference close as cross-check
- Split effective today adjusts the previous close; non-positive ratio blocks the check
- JSON/CSV report with sources, notes and minutes after the US open
- Findings F1–F3 documented in docs/FINDINGS.md
