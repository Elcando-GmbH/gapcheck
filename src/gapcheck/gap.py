"""Opening gap against the previous close.

Rules (see docs/FINDINGS.md for the data errors behind them):

- The previous close is the close of the previous unadjusted daily candle. A vendor's
  "previous close" field is never used (F1).
- An optional reference source (for example the close stored by an overnight job) is a
  cross-check only. A deviation beyond the tolerance is noted, it does not override the
  candle and does not block the check.
- gap = open / previous close - 1, on unadjusted prices.
- A split effective today divides the previous close by the split ratio. A non-positive
  ratio blocks the check instead of producing a wrong gap.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd

from .candles import TickerQuotes

DEFAULT_THRESHOLD = 0.05
DEFAULT_REFERENCE_TOLERANCE = 0.002


class ReferenceClose(Protocol):
    """Independent previous close used as a cross-check. None means not available."""

    name: str

    def prev_close(self, ticker: str, trading_date: dt.date) -> tuple[dt.date, float] | None: ...


class NoReference:
    name = "none"

    def prev_close(self, ticker: str, trading_date: dt.date) -> tuple[dt.date, float] | None:
        return None


class CsvReference:
    """CSV with columns ``ticker``, ``date``, ``close`` (unadjusted)."""

    name = "csv"

    def __init__(self, path: str | Path):
        df = pd.read_csv(path, dtype={"ticker": str})
        cols = {c.lower(): c for c in df.columns}
        missing = [c for c in ("ticker", "date", "close") if c not in cols]
        if missing:
            raise ValueError(f"{path}: missing column(s) {', '.join(missing)}")
        df = df.rename(columns={cols["ticker"]: "ticker", cols["date"]: "date", cols["close"]: "close"})
        df["ticker"] = df["ticker"].str.strip().str.upper()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        self._rows = df.sort_values("date")

    def prev_close(self, ticker: str, trading_date: dt.date) -> tuple[dt.date, float] | None:
        sub = self._rows[(self._rows["ticker"] == ticker) & (self._rows["date"] < trading_date)]
        if sub.empty:
            return None
        last = sub.iloc[-1]
        return last["date"], float(last["close"])


@dataclass
class GapResult:
    ticker: str
    candle_date: dt.date | None
    open: float | None
    open_source: str
    prev_close_candle: float | None
    prev_close_candle_date: dt.date | None
    prev_close_reference: float | None
    prev_close_reference_date: dt.date | None
    prev_close_used: float | None  # after split adjustment
    prev_close_source: str  # "candle" | reference name | "none"
    split_ratio: float | None
    gap: float | None
    triggered: bool
    status: str  # "triggered" | "ok" | "blocked" | "no_data"
    notes: list[str] = field(default_factory=list)


def compute_gap(
    quotes: TickerQuotes,
    reference: ReferenceClose | None = None,
    trading_date: dt.date | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    reference_tolerance: float = DEFAULT_REFERENCE_TOLERANCE,
) -> GapResult:
    reference = reference or NoReference()
    trading_date = trading_date or (quotes.today.date if quotes.today else None)
    r = GapResult(
        ticker=quotes.ticker,
        candle_date=quotes.today.date if quotes.today else None,
        open=quotes.today.open if quotes.today else None,
        open_source=quotes.open_source,
        prev_close_candle=quotes.previous.close if quotes.previous else None,
        prev_close_candle_date=quotes.previous.date if quotes.previous else None,
        prev_close_reference=None,
        prev_close_reference_date=None,
        prev_close_used=None,
        prev_close_source="none",
        split_ratio=None,
        gap=None,
        triggered=False,
        status="no_data",
        notes=list(quotes.notes),
    )

    ref = reference.prev_close(quotes.ticker, trading_date) if trading_date else None
    if ref is not None:
        r.prev_close_reference_date, r.prev_close_reference = ref

    if r.prev_close_candle is not None:
        r.prev_close_used, r.prev_close_source = r.prev_close_candle, "candle"
        if r.prev_close_reference is not None:
            dev = r.prev_close_reference / r.prev_close_candle - 1
            if abs(dev) > reference_tolerance:
                r.notes.append(
                    f"reference close {r.prev_close_reference:.4f} ({r.prev_close_reference_date}) deviates "
                    f"from candle {r.prev_close_candle:.4f} ({dev:+.2%}); candle used"
                )
            elif r.prev_close_reference_date != r.prev_close_candle_date:
                r.notes.append(
                    f"reference close dated {r.prev_close_reference_date}, candle dated {r.prev_close_candle_date}"
                )
    elif r.prev_close_reference is not None:
        r.prev_close_used, r.prev_close_source = r.prev_close_reference, reference.name
        r.notes.append("no previous candle; reference close used")

    if quotes.today is not None and quotes.today.split:
        ratio = quotes.today.split
        if ratio > 0 and r.prev_close_used is not None:
            r.split_ratio = ratio
            r.prev_close_used = r.prev_close_used / ratio
            r.notes.append(f"split {ratio:g}:1 effective today; previous close adjusted")
        else:
            r.notes.append(f"split reported with ratio {ratio!r}; check blocked")
            r.status = "blocked"
            return r

    if r.open is None or r.prev_close_used is None or r.prev_close_used <= 0:
        return r

    r.gap = r.open / r.prev_close_used - 1
    r.triggered = abs(r.gap) >= threshold
    r.status = "triggered" if r.triggered else "ok"
    return r
