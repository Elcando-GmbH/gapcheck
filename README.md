# gapcheck

[![CI](https://github.com/Elcando-GmbH/gapcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/Elcando-GmbH/gapcheck/actions/workflows/ci.yml)

Detect opening gaps on US equities without trusting the first numbers a data feed delivers.

An opening gap is simple arithmetic: today's open divided by yesterday's close, minus one.
The hard part is getting the two inputs right in the minutes after the open, when free
feeds return stale opens, after-hours prices labelled as closes, and preliminary minute
bars. gapcheck encodes the rules that came out of running into each of these.

## What it does

| Input | Rule | Why |
|---|---|---|
| Opening price | First one-minute bar at or after 09:30 New York, at most 5 minutes late (configurable) | Daily candles can carry yesterday's open shortly after the bell ([F2](docs/FINDINGS.md#f2--shortly-after-the-open-the-daily-candle-may-still-carry-yesterdays-open-30-oct-2026)) |
| Fallback open | Daily open, rejected if identical to yesterday's open | A stale value must not produce a gap |
| Previous close | Close of the previous unadjusted daily candle | Convenience "previous close" fields can be after-hours prices ([F1](docs/FINDINGS.md#f1--a-vendors-previous-close-can-be-an-after-hours-price-29-oct-2026)) |
| Reference close | Optional cross-check, deviation noted | Disagreement is information, not an override |
| Split today | Previous close divided by the ratio; non-positive ratio blocks | A split must not look like a −90 % gap |
| Report | Every result with its source, notes and minutes after the open | Early signals are preliminary ([F3](docs/FINDINGS.md#f3--in-the-first-minutes-the-opening-price-is-preliminary-2-and-3-nov-2026)) |

Nothing is downloaded and nothing is written to a price database. You pass in pandas frames
from any source. The output is a report.

## Install

```bash
pip install git+https://github.com/Elcando-GmbH/gapcheck.git
```

Python 3.11 or later. The only dependency is pandas.

## Use

```python
import datetime as dt
from gapcheck import quotes_from_daily, first_minute_open, select_open, compute_gap

day = dt.date(2026, 10, 30)
q = quotes_from_daily(daily_frame, "NOW", day)            # unadjusted daily candles
q = select_open(q, *first_minute_open(minute_frame, day))  # one-minute bars
r = compute_gap(q, trading_date=day, threshold=0.05)

print(r.status, r.gap, r.open_source, r.daily_open, r.notes)
```

`daily_frame` holds unadjusted daily candles (`Open`, `Close`, optionally `Stock Splits`),
`minute_frame` one-minute bars (`Open`) with a timezone-aware or UTC index, both from your
data source. With [yfinance](https://github.com/ranaroussi/yfinance), for example (not a
dependency of this package; check Yahoo's terms before using the data):

```python
import yfinance as yf

daily_frame = yf.download("NOW", period="5d", interval="1d", auto_adjust=False, actions=True,
                          progress=False, multi_level_index=False)
minute_frame = yf.download("NOW", period="1d", interval="1m", auto_adjust=False,
                           progress=False, multi_level_index=False)
```

A runnable walkthrough of all cases, with inline data:

```bash
python examples/walkthrough.py
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

All tests run offline.

## Known limitations

- The opening price is preliminary in the first minutes on the feed tested. From about 30 minutes after the open it matches the final daily open for most tickers; a small structural difference remains for some ([F3](docs/FINDINGS.md#f3--in-the-first-minutes-the-opening-price-is-preliminary-2-and-3-nov-2026)). Two days measured so far.
- If the first one-minute bar is more than 5 minutes late, it is ignored and the daily-open rules apply.
- The split check rejects only non-positive ratios. It does not validate a ratio against the price move.
- Findings are specific to one free feed. The rules are defensive regardless of the source.

## Author

Laura Kruse-Stecher, Elcando GmbH. Equity investor for more than 20 years; builds systematic
equity strategies and the data infrastructure to test them.

## License

MIT, Copyright (c) 2026 Elcando GmbH. For informational purposes only. Not investment advice.
