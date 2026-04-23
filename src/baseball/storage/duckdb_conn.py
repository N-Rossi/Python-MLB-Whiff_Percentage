"""DuckDB connection factory and view registration.

Design: in-memory DuckDB with `read_parquet` glob views over the on-disk
Parquet layout. No persistent database — every connection reads the latest
Parquet. Fast enough for interactive queries and removes any sync concern
between the ingest layer and the query layer.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from loguru import logger

from baseball.config import settings


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a fresh in-memory DuckDB connection with the configured memory cap."""
    con = duckdb.connect(database=":memory:")
    if settings.duckdb_memory_limit:
        con.execute(f"SET memory_limit = '{settings.duckdb_memory_limit}'")
        logger.debug(f"DuckDB memory_limit set to {settings.duckdb_memory_limit}")
    return con


def _register_pitches_view(con: duckdb.DuckDBPyConnection) -> bool:
    parquet_files = list(settings.raw_dir.glob("**/*.parquet"))
    if not parquet_files:
        logger.warning(
            f"No raw Statcast parquet files found at {settings.raw_dir}. "
            "Run `baseball backfill` first — `pitches` view not created."
        )
        return False

    glob = (settings.raw_dir / "**" / "*.parquet").as_posix()
    # Cast hive-partition columns to proper int types — DuckDB infers `month` as
    # VARCHAR because of leading zeros ("04"), which breaks numeric comparisons.
    con.execute(
        f"""
        CREATE OR REPLACE VIEW pitches AS
        SELECT * REPLACE (
            CAST(season AS INTEGER) AS season,
            CAST(month AS SMALLINT) AS month
        )
        FROM read_parquet(
            '{glob}',
            hive_partitioning = true,
            union_by_name = true
        )
        """
    )
    return True


def _register_derived_views(con: duckdb.DuckDBPyConnection) -> list[str]:
    registered: list[str] = []
    for parquet in sorted(settings.derived_dir.glob("*.parquet")):
        name = parquet.stem
        con.execute(
            f"""
            CREATE OR REPLACE VIEW {name} AS
            SELECT * FROM read_parquet('{parquet.as_posix()}')
            """
        )
        registered.append(name)
    return registered


def register_views(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Register every queryable view: `pitches` over raw partitions, plus one
    view per `data/derived/*.parquet` file named after its stem."""
    has_pitches = _register_pitches_view(con)
    derived = _register_derived_views(con)
    return {"pitches": has_pitches, "derived": derived}


def list_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


def table_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    rows = con.execute(f"DESCRIBE {table}").fetchall()
    return [r[0] for r in rows]


def raw_partition_files() -> list[Path]:
    return sorted(settings.raw_dir.glob("**/*.parquet"))
