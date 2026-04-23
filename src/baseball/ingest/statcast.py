"""Chunked Statcast pulls with partitioned Parquet writes.

Pulls one week at a time from Baseball Savant via pybaseball, splits each
week's rows by (year, month), and writes to
    data/raw/statcast/season=YYYY/month=MM.parquet

A sidecar .manifest.json in the raw_dir tracks completed weeks so re-runs
can skip work that's already on disk.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd
from loguru import logger

from baseball.config import (
    BACKFILL_CHUNK_DAYS,
    BACKFILL_SLEEP_SECS,
    PARQUET_COMPRESSION,
    REGULAR_SEASON_END_MMDD,
    REGULAR_SEASON_START_MMDD,
    settings,
)

MANIFEST_FILENAME = ".manifest.json"

# pybaseball returns these ID-ish columns as float64 because of NaN handling.
# Coerce to pandas nullable Int64 so downstream queries don't see 12345.0.
ID_COLUMNS: tuple[str, ...] = (
    "game_pk",
    "pitcher",
    "batter",
    "fielder_2",
    "fielder_3",
    "fielder_4",
    "fielder_5",
    "fielder_6",
    "fielder_7",
    "fielder_8",
    "fielder_9",
    "at_bat_number",
    "pitch_number",
    "inning",
    "home_score",
    "away_score",
    "bat_score",
    "fld_score",
    "post_bat_score",
    "post_fld_score",
    "outs_when_up",
    "balls",
    "strikes",
)


@dataclass
class WeekResult:
    start: dt.date
    end: dt.date
    row_count: int
    duration_secs: float
    was_cached: bool


def iter_weeks(
    start: dt.date, end: dt.date, chunk_days: int = BACKFILL_CHUNK_DAYS
) -> Iterator[tuple[dt.date, dt.date]]:
    cur = start
    while cur <= end:
        nxt = min(cur + dt.timedelta(days=chunk_days - 1), end)
        yield cur, nxt
        cur = nxt + dt.timedelta(days=1)


def season_date_range(season: int) -> tuple[dt.date, dt.date]:
    start = dt.date.fromisoformat(f"{season}-{REGULAR_SEASON_START_MMDD}")
    end = dt.date.fromisoformat(f"{season}-{REGULAR_SEASON_END_MMDD}")
    return start, end


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    for col in ID_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype("Int64")
    return df


def month_partition_path(season: int, month: int) -> Path:
    return settings.raw_dir / f"season={season}" / f"month={month:02d}" / "pitches.parquet"


def _manifest_path() -> Path:
    return settings.raw_dir / MANIFEST_FILENAME


def _load_manifest() -> dict:
    p = _manifest_path()
    if not p.exists():
        return {"completed_weeks": {}}
    return json.loads(p.read_text())


def _save_manifest(m: dict) -> None:
    p = _manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, indent=2, sort_keys=True))


def _week_key(start: dt.date, end: dt.date) -> str:
    return f"{start.isoformat()}..{end.isoformat()}"


def _months_spanned(start: dt.date, end: dt.date) -> set[tuple[int, int]]:
    months: set[tuple[int, int]] = set()
    cur = start
    while cur <= end:
        months.add((cur.year, cur.month))
        cur += dt.timedelta(days=1)
    return months


def _week_already_complete(manifest: dict, start: dt.date, end: dt.date) -> bool:
    key = _week_key(start, end)
    entry = manifest.get("completed_weeks", {}).get(key)
    if entry is None:
        return False
    if entry["row_count"] == 0:
        # Empty weeks (off-days, all-star break) have nothing on disk to verify.
        return True
    return all(month_partition_path(y, m).exists() for y, m in _months_spanned(start, end))


def write_month_partition(df: pd.DataFrame, season: int, month: int) -> int:
    """Merge df into the (season, month) partition, replacing any existing rows
    whose game_date falls inside the new df's date set. Returns the post-write
    row count.
    """
    out_path = month_partition_path(season, month)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        existing = pd.read_parquet(out_path)
        if "game_date" in existing.columns and "game_date" in df.columns:
            new_dates = set(df["game_date"].dt.date.dropna().unique())
            existing = existing[~existing["game_date"].dt.date.isin(new_dates)]
        combined = pd.concat([existing, df], ignore_index=True)
    else:
        combined = df.reset_index(drop=True)

    combined.to_parquet(out_path, compression=PARQUET_COMPRESSION, index=False)
    return len(combined)


def pull_week(start: dt.date, end: dt.date) -> pd.DataFrame:
    """Pull one week from Baseball Savant. pybaseball is imported lazily so
    unit tests for the partition / manifest logic don't require the network."""
    from pybaseball import statcast

    df = statcast(start.isoformat(), end.isoformat(), verbose=False)
    if df is None or df.empty:
        return pd.DataFrame()
    return coerce_types(df)


def ingest_week(start: dt.date, end: dt.date, force: bool = False) -> WeekResult:
    manifest = _load_manifest()
    key = _week_key(start, end)

    if not force and _week_already_complete(manifest, start, end):
        logger.info(f"Week {key} already cached; skipping")
        return WeekResult(
            start, end, manifest["completed_weeks"][key]["row_count"], 0.0, True
        )

    t0 = time.perf_counter()
    df = pull_week(start, end)

    if df.empty:
        logger.info(f"Week {key}: no pitches returned")
        manifest.setdefault("completed_weeks", {})[key] = {
            "row_count": 0,
            "pulled_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        _save_manifest(manifest)
        return WeekResult(start, end, 0, time.perf_counter() - t0, False)

    if "game_date" not in df.columns:
        logger.warning(f"Week {key}: response missing game_date column; skipping")
        return WeekResult(start, end, 0, time.perf_counter() - t0, False)

    df = df.assign(
        _y=df["game_date"].dt.year,
        _m=df["game_date"].dt.month,
    )
    row_count = 0
    for (season, month), grp in df.groupby(["_y", "_m"], dropna=True):
        grp = grp.drop(columns=["_y", "_m"])
        total_after = write_month_partition(grp, int(season), int(month))
        logger.info(
            f"  season={int(season)}/month={int(month):02d}: "
            f"+{len(grp):,} rows (partition now {total_after:,})"
        )
        row_count += len(grp)

    duration = time.perf_counter() - t0
    logger.info(f"Week {key}: pulled {row_count:,} pitches in {duration:.1f}s")

    manifest.setdefault("completed_weeks", {})[key] = {
        "row_count": row_count,
        "pulled_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    _save_manifest(manifest)
    return WeekResult(start, end, row_count, duration, False)


def ingest_season(
    season: int,
    force: bool = False,
    sleep_secs: float = BACKFILL_SLEEP_SECS,
) -> list[WeekResult]:
    start, end = season_date_range(season)
    results: list[WeekResult] = []
    logger.info(f"Ingesting season {season}: {start} .. {end}")
    for ws, we in iter_weeks(start, end):
        try:
            result = ingest_week(ws, we, force=force)
        except Exception as ex:
            logger.error(f"Week {ws}..{we} FAILED: {ex.__class__.__name__}: {ex}")
            continue
        results.append(result)
        if not result.was_cached:
            time.sleep(sleep_secs)
    total = sum(r.row_count for r in results)
    logger.info(f"Season {season} done: {total:,} pitches across {len(results)} weeks")
    return results


def ingest_date(date: dt.date, force: bool = False) -> WeekResult:
    """One-day pull — used by the nightly `update` command."""
    return ingest_week(date, date, force=force)
