"""Daily candles and the choice of the opening price.

Rules, each backed by an observed data error (see docs/FINDINGS.md):

1. The opening price is the open of the first one-minute bar at or after 09:30 New York.
   Shortly after the open, the daily candle of a free data feed may still carry the
   previous day's open (F2).
2. If no one-minute bar is available, the daily open is used only if it differs from the
   previous day's open. An identical value is treated as stale and rejected.
3. A daily open that deviates from the one-minute open by more than a tolerance is kept in
   the notes, so the discrepancy stays visible in the report.

Nothing here downloads data. Callers pass in pandas frames from any source with the
columns ``Open``, ``Close`` and optionally ``High``, ``Low``, ``Volume``, ``Stock Splits``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from .sessions import NEW_YORK, US_OPEN

DAILY_VS_MINUTE_TOLERANCE = 0.005


@dataclass
class Candle:
    date: dt.date
    open: float | None
    close: float | None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    split: float = 0.0  # split ratio effective on this date, 0 = none


@dataclass
class TickerQuotes:
    """Today's candle and the last candle before today, plus how the open was chosen."""

    ticker: str
    today: Candle | None
    previous: Candle | None
    notes: list[str] = field(default_factory=list)
    open_source: str = "daily"  # "minute_bar" | "daily" | "none"

    @property
    def usable(self) -> bool:
        return (
            self.today is not None
            and self.today.open is not None
            and self.previous is not None
            and self.previous.close is not None
        )


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _candle(index_value, row: pd.Series) -> Candle:
    return Candle(
        date=pd.Timestamp(index_value).date(),
        open=_num(row.get("Open")),
        close=_num(row.get("Close")),
        high=_num(row.get("High")),
        low=_num(row.get("Low")),
        volume=_num(row.get("Volume")),
        split=_num(row.get("Stock Splits")) or 0.0,
    )


def quotes_from_daily(frame: pd.DataFrame | None, ticker: str, trading_date: dt.date) -> TickerQuotes:
    """Pick today's candle and the previous candle from a frame of unadjusted daily candles."""
    q = TickerQuotes(ticker=ticker, today=None, previous=None)
    if frame is None or frame.empty:
        q.notes.append("no daily candles")
        return q
    frame = frame.dropna(how="all", subset=[c for c in ("Open", "Close") if c in frame.columns])
    if frame.empty:
        q.notes.append("no daily candles with open or close")
        return q
    candles = sorted((_candle(i, r) for i, r in frame.iterrows()), key=lambda c: c.date)
    today = [c for c in candles if c.date == trading_date]
    before = [c for c in candles if c.date < trading_date]
    if today:
        q.today = today[-1]
        if q.today.open is None:
            q.notes.append("today's candle has no open")
    else:
        q.notes.append(f"no candle for {trading_date.isoformat()} (last: {candles[-1].date.isoformat()})")
    if before:
        q.previous = before[-1]
        if q.previous.close is None:
            q.notes.append("previous candle has no close")
    else:
        q.notes.append("no previous candle")
    return q


def first_minute_open(frame: pd.DataFrame | None, trading_date: dt.date) -> tuple[float | None, str | None]:
    """Open of the first one-minute bar at or after 09:30 New York. Returns (open, 'HH:MM')."""
    if frame is None or frame.empty or "Open" not in frame.columns:
        return None, None
    idx = pd.DatetimeIndex(frame.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx
    f = frame.copy()
    f.index = idx.tz_convert(NEW_YORK)
    f = f[(f.index.date == trading_date) & (f.index.time >= US_OPEN)]
    f = f[f["Open"].notna()]
    if f.empty:
        return None, None
    return _num(f["Open"].iloc[0]), f.index[0].strftime("%H:%M")


def select_open(
    quotes: TickerQuotes,
    minute_open: float | None,
    minute_time: str | None,
    tolerance: float = DAILY_VS_MINUTE_TOLERANCE,
) -> TickerQuotes:
    """Set today's opening price according to the rules in the module docstring."""
    if quotes.today is None:
        quotes.open_source = "none"
        return quotes
    daily_open = quotes.today.open

    if minute_open is not None:
        quotes.today.open = minute_open
        quotes.open_source = "minute_bar"
        if minute_time != US_OPEN.strftime("%H:%M"):
            quotes.notes.append(f"first one-minute bar only at {minute_time} New York")
        if daily_open is not None and abs(daily_open / minute_open - 1) > tolerance:
            quotes.notes.append(
                f"daily open {daily_open:.4f} deviates from one-minute open {minute_open:.4f}; minute bar used"
            )
        return quotes

    prev_open = quotes.previous.open if quotes.previous else None
    if daily_open is not None and prev_open is not None and daily_open == prev_open:
        quotes.today.open = None
        quotes.open_source = "none"
        quotes.notes.append(
            f"no one-minute bar; daily open {daily_open:.4f} equals previous open, rejected as stale"
        )
        return quotes

    quotes.open_source = "daily" if daily_open is not None else "none"
    if daily_open is not None:
        quotes.notes.append("no one-minute bar; daily open used")
    return quotes
