"""gapcheck: detect opening gaps on US equities without trusting the first numbers a feed delivers."""

__version__ = "0.1.2"

from .candles import Candle, TickerQuotes, first_minute_open, quotes_from_daily, select_open
from .gap import CsvReference, GapResult, NoReference, ReferenceClose, compute_gap
from .report import build_report, write_report
from .sessions import minutes_after_open, us_open, us_trading_date

__all__ = [
    "Candle",
    "CsvReference",
    "GapResult",
    "NoReference",
    "ReferenceClose",
    "TickerQuotes",
    "build_report",
    "compute_gap",
    "first_minute_open",
    "minutes_after_open",
    "quotes_from_daily",
    "select_open",
    "us_open",
    "us_trading_date",
    "write_report",
]
