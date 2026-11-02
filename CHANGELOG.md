# Changelog

## 0.1.0 — 2026-11-02

First public release.

- Opening price from the first one-minute bar at or after 09:30 New York; stale daily open rejected
- Previous close from the unadjusted daily candle; optional reference close as cross-check
- Split effective today adjusts the previous close; non-positive ratio blocks the check
- JSON/CSV report with sources, notes and minutes after the US open
- Findings F1–F3 documented in docs/FINDINGS.md
