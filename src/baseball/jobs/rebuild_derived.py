"""Orchestrator for rebuilding derived Parquet tables from raw pitch data."""

from __future__ import annotations

from typing import Callable

import duckdb
from loguru import logger

from baseball.derived.pitcher_tables import build_pitcher_pitch_mix
from baseball.storage.duckdb_conn import get_connection, register_views

# Order matters once tables start depending on one another (e.g., matchup_edges
# joins pitcher and batter tables). For now there's only one.
REGISTRY: dict[str, Callable[[duckdb.DuckDBPyConnection], None]] = {
    "pitcher_pitch_mix": build_pitcher_pitch_mix,
}


def rebuild_one(table: str) -> None:
    if table not in REGISTRY:
        raise ValueError(
            f"Unknown derived table: {table!r}. Available: {sorted(REGISTRY)}"
        )
    con = get_connection()
    register_views(con)
    REGISTRY[table](con)


def rebuild_all() -> None:
    con = get_connection()
    register_views(con)
    logger.info(f"Rebuilding {len(REGISTRY)} derived tables: {sorted(REGISTRY)}")
    for name, fn in REGISTRY.items():
        fn(con)
    logger.info("All derived tables rebuilt")
