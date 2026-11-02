import datetime as dt
from pathlib import Path

import pytest

from gapcheck import Candle, CsvReference, NoReference, TickerQuotes, compute_gap

D = dt.date(2026, 10, 29)
PREV = dt.date(2026, 10, 28)


def tq(open_today, prev_close, split=0.0, today=True, previous=True):
    return TickerQuotes(
        "FTNT",
        today=Candle(D, open=open_today, close=None, split=split) if today else None,
        previous=Candle(PREV, open=None, close=prev_close) if previous else None,
    )


def test_gap_from_candles():
    r = compute_gap(tq(127.67, 174.08), trading_date=D)
    assert r.gap == pytest.approx(127.67 / 174.08 - 1)
    assert r.triggered and r.status == "triggered" and r.prev_close_source == "candle"


def test_below_threshold():
    r = compute_gap(tq(100.0, 98.0), trading_date=D)
    assert not r.triggered and r.status == "ok"


def test_threshold_is_inclusive():
    assert compute_gap(tq(105.0, 100.0), trading_date=D, threshold=0.05).triggered


def test_custom_threshold():
    assert not compute_gap(tq(105.0, 100.0), trading_date=D, threshold=0.06).triggered


def test_reference_agrees(tmp_path: Path):
    f = tmp_path / "ref.csv"
    f.write_text("ticker,date,close\nFTNT,2026-10-27,172.0\nFTNT,2026-10-28,174.08\n")
    r = compute_gap(tq(127.67, 174.08), CsvReference(f), D)
    assert r.prev_close_reference == 174.08 and not r.notes


def test_wrong_reference_is_noted_but_candle_wins(tmp_path: Path):
    # 29.10.2026: a vendor "previous close" showed the after-hours price 129.33 (F1)
    f = tmp_path / "ref.csv"
    f.write_text("ticker,date,close\nFTNT,2026-10-28,129.33\n")
    r = compute_gap(tq(127.67, 174.08), CsvReference(f), D)
    assert r.prev_close_used == 174.08 and r.prev_close_source == "candle"
    assert r.triggered
    assert any("deviates" in n for n in r.notes)


def test_reference_date_mismatch_is_noted(tmp_path: Path):
    f = tmp_path / "ref.csv"
    f.write_text("ticker,date,close\nFTNT,2026-10-27,174.08\n")
    r = compute_gap(tq(127.67, 174.08), CsvReference(f), D)
    assert any("dated 2026-10-27" in n for n in r.notes)


def test_reference_used_only_without_candle(tmp_path: Path):
    f = tmp_path / "ref.csv"
    f.write_text("ticker,date,close\nFTNT,2026-10-28,174.08\n")
    r = compute_gap(tq(127.67, None, previous=False), CsvReference(f), D)
    assert r.prev_close_source == "csv" and r.triggered


def test_split_today_adjusts_previous_close():
    # 10:1 split: previous close 1000, open 101 -> +1 %, not -89.9 %
    r = compute_gap(tq(101.0, 1000.0, split=10.0), trading_date=D)
    assert r.split_ratio == 10.0 and r.prev_close_used == pytest.approx(100.0)
    assert r.gap == pytest.approx(0.01) and not r.triggered


def test_implausible_split_blocks():
    r = compute_gap(tq(101.0, 1000.0, split=-2.0), trading_date=D)
    assert r.status == "blocked" and r.gap is None and not r.triggered


def test_no_data():
    r = compute_gap(tq(None, 174.08, today=False), NoReference(), D)
    assert r.status == "no_data" and r.gap is None


def test_csv_reference_requires_columns(tmp_path: Path):
    f = tmp_path / "bad.csv"
    f.write_text("symbol,close\nX,1\n")
    with pytest.raises(ValueError, match="ticker"):
        CsvReference(f)
