"""Nightly in-season cron entrypoint.

Flow:
    1. Ingest the last N days of Statcast pitches (default: 1 = yesterday).
       Days already cached in the manifest are skipped unless --force.
    2. If any new pitches were ingested, rebuild all derived tables so
       `matchup_edges` and the `_shrunk` columns reflect the latest data.
    3. Exit 0 on success, non-zero if any day failed to ingest or if the
       rebuild raised.

Intended invocation (any of these):
    baseball daily-update                          # yesterday only
    baseball daily-update --days 3                 # catch up last 3 days
    baseball daily-update --skip-rebuild           # ingest only
    baseball daily-update --force                  # re-pull even if cached
    python -m baseball.jobs.daily_update --days 3  # same thing, no CLI needed

Logging goes to stderr by default. Set `BASEBALL_DAILY_LOG_DIR=/path/to/dir`
to additionally tee to `<dir>/daily_update_YYYYMMDD.log` (rotated at 7 days,
kept for 30).
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from loguru import logger

from baseball.ingest.statcast import ingest_date
from baseball.jobs.rebuild_derived import rebuild_all


def _configure_file_logging() -> None:
    log_dir = os.environ.get("BASEBALL_DAILY_LOG_DIR")
    if not log_dir:
        return
    log_path = Path(log_dir) / f"daily_update_{dt.date.today():%Y%m%d}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        rotation="7 days",
        retention="30 days",
        level="INFO",
        enqueue=True,
    )


def run(days: int = 1, skip_rebuild: bool = False, force: bool = False) -> int:
    """Execute the daily update. Returns a shell exit code (0 = success)."""
    if days < 1:
        logger.error("--days must be >= 1")
        return 2

    _configure_file_logging()

    today = dt.date.today()
    targets = [today - dt.timedelta(days=i) for i in range(1, days + 1)]
    targets.reverse()  # oldest first, so output reads chronologically

    logger.info(
        f"Daily update starting: {len(targets)} day(s) "
        f"({targets[0]} .. {targets[-1]}); force={force}, skip_rebuild={skip_rebuild}"
    )

    failures: list[tuple[dt.date, str]] = []
    fresh_rows = 0
    fresh_days = 0

    for d in targets:
        try:
            result = ingest_date(d, force=force)
        except Exception as ex:  # noqa: BLE001  — we want to keep going on other days
            logger.error(f"Ingest failed for {d}: {ex.__class__.__name__}: {ex}")
            failures.append((d, f"{ex.__class__.__name__}: {ex}"))
            continue
        if not result.was_cached:
            fresh_rows += result.row_count
            if result.row_count > 0:
                fresh_days += 1

    logger.info(
        f"Ingest summary: {fresh_days}/{len(targets)} day(s) had new pitches "
        f"({fresh_rows:,} total pitches)"
    )

    if failures:
        logger.error(f"{len(failures)} day(s) failed — NOT running derived rebuild")
        for d, err in failures:
            logger.error(f"  {d}: {err}")
        return 1

    if skip_rebuild:
        logger.info("--skip-rebuild set; leaving derived tables alone")
        return 0

    if fresh_rows == 0:
        logger.info("No new pitches ingested; skipping derived rebuild")
        return 0

    logger.info("Rebuilding all derived tables")
    try:
        rebuild_all()
    except Exception as ex:  # noqa: BLE001
        logger.error(f"Derived rebuild FAILED: {ex.__class__.__name__}: {ex}")
        return 1

    logger.info("Daily update complete")
    return 0


# `python -m baseball.jobs.daily_update` entry point for environments where
# the `baseball` console script isn't on PATH.
if __name__ == "__main__":
    import sys

    import typer

    def _main(
        days: int = typer.Option(1, "--days"),
        skip_rebuild: bool = typer.Option(False, "--skip-rebuild"),
        force: bool = typer.Option(False, "--force"),
    ) -> None:
        sys.exit(run(days=days, skip_rebuild=skip_rebuild, force=force))

    typer.run(_main)
