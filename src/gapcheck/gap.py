"""Opening gap against the previous close.

Rules (see docs/FINDINGS.md for the data errors behind them):

- The previous close is the close of the previous unadjusted daily candle. A vendor's
  "previous close" field is never used (F1).
- An optional reference source (for example the close stored by an overnight job) is a
  cross-check only. A deviation beyond the tolerance is noted, it does not override the
  candle and does not block the check.
- gap = open / previous close - 1, on unadjusted prices. The threshold comparison allows
  for floating-point rounding (1e-12), so a gap of exactly the threshold counts as triggered.
- A split effective today: many feeds deliver the history already split-adjusted, even when
  asked for unadjusted prices (F4). ``history_split_adjusted=True`` (default) takes the previous
  close as adjusted and does not divide again. With ``False`` the previous close is divided by
  the split ratio. A non-positive ratio blocks the check instead of producing a wrong gap.
- If open and previous close (after any split handling) still stand in the ratio of a common
  split, the check is blocked with a note: either a split is not reported, or
  ``history_split_adjusted`` does not match the data. A split must never look like a gap.
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
THRESHOLD_EPSILON = 1e-12
SPLIT_RATIOS = (2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 50)
SPLIT_TOLERANCE = 0.03


def split_like(prev_close: float, price: float) -> float | None:
    """Ratio of a common split (negative = reverse split) if prev_close / price matches one."""
    if prev_close <= 0 or price <= 0:
        return None
    q = prev_close / price
    for ratio in SPLIT_RATIOS:
        if abs(q / ratio - 1) <= SPLIT_TOLERANCE:
            return float(ratio)
        if abs(q * ratio - 1) <= SPLIT_TOLERANCE:
            return -float(ratio)
    return None


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
    daily_open: float | None  # daily open as delivered by the feed
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
    history_split_adjusted: bool = True,
) -> GapResult:
    reference = reference or NoReference()
    trading_date = trading_date or (quotes.today.date if quotes.today else None)
    r = GapResult(
        ticker=quotes.ticker,
        candle_date=quotes.today.date if quotes.today else None,
        open=quotes.today.open if quotes.today else None,
        open_source=quotes.open_source,
        daily_open=quotes.daily_open if quotes.daily_open is not None else (quotes.today.open if quotes.today else None),
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

    split_reported = quotes.today is not None and bool(quotes.today.split)
    if split_reported:
        ratio = quotes.today.split
        if ratio <= 0 or r.prev_close_used is None:
            r.notes.append(f"split reported with ratio {ratio!r}; check blocked")
            r.status = "blocked"
            return r
        r.split_ratio = ratio
        if history_split_adjusted:
            r.notes.append(f"split {ratio:g}:1 effective today; previous close taken as already split-adjusted")
        else:
            r.prev_close_used = r.prev_close_used / ratio
            r.notes.append(f"split {ratio:g}:1 effective today; previous close divided by the ratio")

    if r.open is None or r.prev_close_used is None or r.prev_close_used <= 0:
        return r

    residual = split_like(r.prev_close_used, r.open)
    if residual is not None:
        kind = "split" if residual > 0 else "reverse-split"
        why = ("history_split_adjusted does not match the data" if split_reported
               else "but no split is reported")
        r.notes.append(
            f"open {r.open:.4f} and previous close {r.prev_close_used:.4f} stand in a {abs(residual):g}:1 "
            f"{kind} ratio, {why}; check blocked"
        )
        r.status = "blocked"
        return r

    r.gap = r.open / r.prev_close_used - 1
    r.triggered = abs(r.gap) >= threshold - THRESHOLD_EPSILON
    r.status = "triggered" if r.triggered else "ok"
    return r
