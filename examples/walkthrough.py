"""Walk through the three data errors gapcheck guards against, on small inline frames.

Prices are illustrative and modelled on cases observed in October and November 2026
(docs/FINDINGS.md). No data is downloaded.

    python examples/walkthrough.py
"""

import datetime as dt

import pandas as pd

from gapcheck import (
    Candle,
    TickerQuotes,
    build_report,
    compute_gap,
    first_minute_open,
    quotes_from_daily,
    select_open,
)

DAY = dt.date(2026, 10, 30)


def daily(rows):
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame({"Open": [r[1] for r in rows], "Close": [r[2] for r in rows]}, index=idx)


def minutes(times, opens):
    idx = pd.DatetimeIndex([pd.Timestamp(f"{DAY} {t}", tz="America/New_York") for t in times])
    return pd.DataFrame({"Open": opens}, index=idx)


cases = {
    # Daily candle still shows yesterday's open (120.905 vs close 109.67 = a false +10.2 % gap);
    # the 09:30 minute bar has the real open.
    "STALE": (daily([("2026-10-29", 120.905, 109.67), ("2026-10-30", 120.905, 111.00)]),
              minutes(["09:30", "09:31"], [110.20, 110.90])),
    # No minute bar and the daily open equals yesterday's open: rejected, no false gap.
    "NOBAR": (daily([("2026-10-29", 50.00, 48.00), ("2026-10-30", 50.00, 47.50)]), None),
    # A genuine gap, confirmed by the minute bar.
    "GAP": (daily([("2026-10-29", 93.00, 92.07), ("2026-10-30", 68.35, 69.00)]),
            minutes(["09:30"], [68.35])),
}

results = []
for ticker, (day_frame, minute_frame) in cases.items():
    q = quotes_from_daily(day_frame, ticker, DAY)
    q = select_open(q, *first_minute_open(minute_frame, DAY))
    results.append(compute_gap(q, trading_date=DAY))

# A split effective today: the previous close is divided by the ratio.
split = TickerQuotes("SPLIT", today=Candle(DAY, open=101.0, close=None, split=10.0),
                     previous=Candle(dt.date(2026, 10, 29), open=None, close=1000.0))
results.append(compute_gap(split, trading_date=DAY))

for r in results:
    gap = "  n/a  " if r.gap is None else f"{r.gap:+7.2%}"
    print(f"{r.ticker:6} {r.status:9} gap {gap}  open from {r.open_source:10}  {'; '.join(r.notes)}")

report = build_report(results, trading_date=DAY, threshold=0.05,
                      data_as_of=dt.datetime(2026, 10, 30, 13, 41, tzinfo=dt.UTC),
                      data_source="inline example")
print("\nsummary:", report["summary"])
