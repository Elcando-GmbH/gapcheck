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


def test_threshold_boundary_with_float_rounding():
    # 0.0735 / 0.07 - 1 evaluates to 0.04999999999999982; an exact 5 % gap must still trigger
    r = compute_gap(tq(0.0735, 0.07), trading_date=D, threshold=0.05)
    assert r.gap < 0.05 and r.triggered


def test_daily_open_in_result():
    q = tq(127.67, 174.08)
    q.daily_open = 130.0
    assert compute_gap(q, trading_date=D).daily_open == 130.0


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


def test_split_today_unadjusted_history_divides():
    # 10:1 split, history not adjusted: previous close 1000, open 101 -> +1 %, not -89.9 %
    r = compute_gap(tq(101.0, 1000.0, split=10.0), trading_date=D, history_split_adjusted=False)
    assert r.split_ratio == 10.0 and r.prev_close_used == pytest.approx(100.0)
    assert r.gap == pytest.approx(0.01) and not r.triggered


@pytest.mark.parametrize(
    "open_, prev, ratio",
    [  # F4: previous close as delivered after the split, already adjusted
        (80.82, 80.04, 2.0),
        (237.60, 241.16, 10.0),
        (166.25, 167.77, 25.0),
        (191.26, 193.18, 4.0),
    ],
)
def test_split_today_adjusted_history_is_default(open_, prev, ratio):
    r = compute_gap(tq(open_, prev, split=ratio), trading_date=D)
    assert r.prev_close_used == prev and abs(r.gap) < 0.02 and not r.triggered
    assert any("already split-adjusted" in n for n in r.notes)


def test_unreported_split_blocks():
    r = compute_gap(tq(193.98, 772.74), trading_date=D)  # 4:1 in the prices, no split reported
    assert r.status == "blocked" and r.gap is None and not r.triggered
    assert any("4:1 split ratio" in n for n in r.notes)


def test_unreported_reverse_split_blocks():
    r = compute_gap(tq(20.0, 2.0), trading_date=D)
    assert r.status == "blocked" and any("reverse-split" in n for n in r.notes)


def test_wrong_history_flag_blocks_instead_of_false_gap():
    # history actually unadjusted, caller left the default (adjusted): prices still show 10:1
    r = compute_gap(tq(101.0, 1000.0, split=10.0), trading_date=D)
    assert r.status == "blocked" and "does not match" in " ".join(r.notes)
    # history actually adjusted, caller says unadjusted: division leaves a 1:10 ratio
    r = compute_gap(tq(237.60, 241.16, split=10.0), trading_date=D, history_split_adjusted=False)
    assert r.status == "blocked" and not r.triggered


def test_large_gap_not_near_a_split_ratio_triggers():
    r = compute_gap(tq(127.67, 174.08), trading_date=D)  # -26.7 %
    assert r.status == "triggered"


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
