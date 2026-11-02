"""Run report: every result, every note, and the context needed to audit it later.

A report records when the check ran relative to the US open, the threshold, a hash of the
ticker list and the package version. Two reports can therefore be compared, for example a
run 10 minutes after the open against one 30 minutes after (see docs/FINDINGS.md, F3).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from . import __version__
from .gap import GapResult
from .sessions import minutes_after_open


def _jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def tickers_sha256(tickers: Iterable[str]) -> str:
    joined = "\n".join(sorted({t.strip().upper() for t in tickers if t.strip()}))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def build_report(
    results: list[GapResult],
    *,
    trading_date: dt.date,
    threshold: float,
    data_as_of: dt.datetime,
    data_source: str = "unspecified",
) -> dict[str, Any]:
    tickers = [r.ticker for r in results]
    status = [r.status for r in results]
    return {
        "gapcheck_version": __version__,
        "trading_date": trading_date.isoformat(),
        "data_as_of_utc": data_as_of.astimezone(dt.UTC).isoformat(),
        "minutes_after_us_open": round(minutes_after_open(data_as_of, trading_date), 1),
        "threshold": threshold,
        "data_source": data_source,
        "universe": {"count": len(tickers), "sha256": tickers_sha256(tickers)},
        "summary": {
            "checked": sum(s in ("ok", "triggered") for s in status),
            "triggered": status.count("triggered"),
            "blocked": status.count("blocked"),
            "no_data": status.count("no_data"),
            "open_source": {s: sum(r.open_source == s for r in results) for s in ("minute_bar", "daily", "none")},
        },
        "results": [_jsonable(r) for r in results],
    }


def write_report(report: dict[str, Any], out_dir: str | Path) -> tuple[Path, Path]:
    """Write ``<out_dir>/<date>/gapcheck_<date>_<HHMMSS-UTC>.json`` and ``.csv``."""
    stamp = dt.datetime.fromisoformat(report["data_as_of_utc"]).strftime("%H%M%S")
    folder = Path(out_dir) / report["trading_date"]
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"gapcheck_{report['trading_date']}_{stamp}"
    json_path, csv_path = base.with_suffix(".json"), base.with_suffix(".csv")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = [
        {
            "ticker": r["ticker"],
            "status": r["status"],
            "open": r["open"],
            "open_source": r["open_source"],
            "prev_close_used": r["prev_close_used"],
            "prev_close_source": r["prev_close_source"],
            "split_ratio": r["split_ratio"],
            "gap_pct": None if r["gap"] is None else round(r["gap"] * 100, 4),
            "notes": " | ".join(r["notes"]),
        }
        for r in report["results"]
    ]
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return json_path, csv_path
