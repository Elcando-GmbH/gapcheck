"""US session calendar helpers.

The US and Europe switch daylight saving time on different dates. For a few weeks each
spring and autumn the US open is 14:30 in Berlin instead of 15:30. These helpers derive
the open from the New York clock, so the offset is always right.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
US_OPEN = dt.time(9, 30)


def us_trading_date(now: dt.datetime | None = None) -> dt.date:
    """Calendar date in New York. Daily candles carry this date."""
    now = now or dt.datetime.now(tz=dt.UTC)
    return now.astimezone(NEW_YORK).date()


def us_open(day: dt.date, tz: str = "America/New_York") -> dt.datetime:
    """09:30 New York on ``day``, expressed in ``tz``."""
    open_ny = dt.datetime.combine(day, US_OPEN, tzinfo=NEW_YORK)
    return open_ny.astimezone(ZoneInfo(tz))


def minutes_after_open(moment: dt.datetime, day: dt.date | None = None) -> float:
    """Minutes between the US open and ``moment`` (negative before the open)."""
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    day = day or moment.astimezone(NEW_YORK).date()
    return (moment - us_open(day)).total_seconds() / 60
