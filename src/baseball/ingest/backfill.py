"""One-time 2015-through-current-season backfill of raw Statcast data."""

from __future__ import annotations

from loguru import logger

from baseball.config import FIRST_STATCAST_SEASON
from baseball.ingest.statcast import WeekResult, ingest_season


def run_backfill(
    start_season: int = FIRST_STATCAST_SEASON,
    end_season: int | None = None,
    force: bool = False,
) -> dict[int, list[WeekResult]]:
    if end_season is None:
        import datetime as dt

        end_season = dt.date.today().year

    if start_season > end_season:
        raise ValueError(f"start_season ({start_season}) > end_season ({end_season})")

    logger.info(f"Backfill: seasons {start_season}..{end_season}")
    results: dict[int, list[WeekResult]] = {}
    for season in range(start_season, end_season + 1):
        results[season] = ingest_season(season, force=force)

    total = sum(r.row_count for season_results in results.values() for r in season_results)
    logger.info(f"Backfill complete: {total:,} total pitches across {len(results)} seasons")
    return results
