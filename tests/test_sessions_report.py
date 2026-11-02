import datetime as dt
import json

import pytest

from gapcheck import Candle, TickerQuotes, build_report, compute_gap, minutes_after_open, us_open, write_report


@pytest.mark.parametrize(
    "day,expected",
    [
        (dt.date(2026, 10, 29), "14:30"),  # Europe already on winter time, US not yet
        (dt.date(2026, 11, 2), "15:30"),
        (dt.date(2027, 3, 15), "14:30"),  # US on summer time, Europe not yet
        (dt.date(2026, 7, 1), "15:30"),
    ],
)
def test_us_open_in_berlin(day, expected):
    assert us_open(day, "Europe/Berlin").strftime("%H:%M") == expected


def test_minutes_after_open():
    t = dt.datetime(2026, 11, 2, 14, 40, tzinfo=dt.UTC)  # 15:40 Berlin
    assert minutes_after_open(t) == pytest.approx(10.0)


def test_minutes_after_open_requires_tz():
    with pytest.raises(ValueError):
        minutes_after_open(dt.datetime(2026, 11, 2, 14, 40))


def _result(ticker, open_, prev):
    d = dt.date(2026, 11, 2)
    q = TickerQuotes(ticker, today=Candle(d, open=open_, close=None), previous=Candle(dt.date(2026, 10, 30), open=None, close=prev))
    q.open_source = "minute_bar"
    return compute_gap(q, trading_date=d)


def test_report_roundtrip(tmp_path):
    results = [_result("IDXX", 621.22, 551.21), _result("AAPL", 100.0, 99.5)]
    rep = build_report(
        results,
        trading_date=dt.date(2026, 11, 2),
        threshold=0.05,
        data_as_of=dt.datetime(2026, 11, 2, 14, 40, 4, tzinfo=dt.UTC),
        data_source="example",
    )
    assert rep["minutes_after_us_open"] == pytest.approx(10.1)
    assert rep["summary"]["triggered"] == 1 and rep["summary"]["checked"] == 2
    assert rep["summary"]["open_source"]["minute_bar"] == 2
    j, c = write_report(rep, tmp_path)
    assert j.name == "gapcheck_2026-11-02_144004.json" and c.exists()
    assert json.loads(j.read_text())["results"][0]["ticker"] == "IDXX"
    assert "daily_open" in c.read_text().splitlines()[0]


def test_version_single_source():
    import importlib.metadata

    import gapcheck

    assert importlib.metadata.version("gapcheck") == gapcheck.__version__
