import datetime as dt

import pandas as pd

from gapcheck import Candle, TickerQuotes, first_minute_open, quotes_from_daily, select_open

D = dt.date(2026, 10, 30)
PREV = dt.date(2026, 10, 29)


def daily(rows):
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "Close": [r[2] for r in rows],
            "Stock Splits": [r[3] if len(r) > 3 else 0.0 for r in rows],
        },
        index=idx,
    )


def minutes(times_ny, opens, day="2026-10-30"):
    idx = pd.DatetimeIndex([pd.Timestamp(f"{day} {t}", tz="America/New_York") for t in times_ny])
    return pd.DataFrame({"Open": opens}, index=idx)


def test_today_and_previous_candle():
    q = quotes_from_daily(daily([("2026-10-28", 170.0, 172.0), ("2026-10-29", 173.0, 174.08), ("2026-10-30", 127.67, 137.64)]), "X", D)
    assert q.usable
    assert q.today.open == 127.67
    assert q.previous.close == 174.08 and q.previous.date == PREV


def test_missing_today_candle_is_noted():
    q = quotes_from_daily(daily([("2026-10-28", 170.0, 172.0), ("2026-10-29", 173.0, 174.08)]), "X", D)
    assert q.today is None and q.previous is not None
    assert any("no candle for 2026-10-30" in n for n in q.notes)


def test_empty_frame():
    q = quotes_from_daily(pd.DataFrame(), "X", D)
    assert not q.usable and q.notes


def test_all_nan_rows_dropped():
    fr = daily([("2026-10-29", 173.0, 174.08), ("2026-10-30", float("nan"), float("nan"))])
    q = quotes_from_daily(fr, "X", D)
    assert q.today is None and q.previous.close == 174.08


def test_first_minute_open_picks_0930():
    assert first_minute_open(minutes(["09:30", "09:31"], [68.35, 69.0]), D) == (68.35, "09:30")


def test_first_minute_open_ignores_premarket_and_handles_utc_index():
    fr = minutes(["09:15", "09:33", "09:34"], [65.0, 70.0, 70.1])
    fr.index = fr.index.tz_convert("UTC")
    assert first_minute_open(fr, D) == (70.0, "09:33")


def test_first_minute_open_empty():
    assert first_minute_open(pd.DataFrame(), D) == (None, None)
    assert first_minute_open(None, D) == (None, None)


def stale(daily_open, prev_open):
    return TickerQuotes("NOW", today=Candle(D, open=daily_open, close=None),
                        previous=Candle(PREV, open=prev_open, close=109.67))


def test_minute_bar_overrides_stale_daily_open():
    # 30.10.2026, +11 min: daily candle still carried the previous day's open (F2)
    q = select_open(stale(120.905, 120.905), 110.2, "09:30")
    assert q.today.open == 110.2 and q.open_source == "minute_bar"
    assert any("deviates" in n for n in q.notes)


def test_stale_daily_open_rejected_without_minute_bar():
    q = select_open(stale(120.905, 120.905), None, None)
    assert q.today.open is None and q.open_source == "none"
    assert any("rejected as stale" in n for n in q.notes)


def test_fresh_daily_open_used_without_minute_bar():
    q = select_open(stale(68.35, 93.0), None, None)
    assert q.today.open == 68.35 and q.open_source == "daily"


def test_late_first_bar_is_noted():
    q = select_open(stale(110.0, 120.0), 110.1, "09:32")
    assert any("09:32" in n for n in q.notes)


def test_no_today_candle():
    q = TickerQuotes("X", today=None, previous=Candle(PREV, open=1.0, close=1.0))
    assert select_open(q, 1.0, "09:30").open_source == "none"
