"""Shared helpers for derived-table builds."""

from __future__ import annotations

from pathlib import Path

import duckdb
from loguru import logger

from baseball.config import PARQUET_COMPRESSION, settings


def write_derived_parquet(
    con: duckdb.DuckDBPyConnection,
    select_sql: str,
    table_name: str,
) -> Path:
    """Write a SELECT query's result to data/derived/<table_name>.parquet.

    Uses DuckDB's native COPY TO rather than a pandas round-trip — it streams
    directly to disk and is orders of magnitude faster for large aggregates.
    """
    out_path = settings.derived_dir / f"{table_name}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Dropping the view first avoids any file-handle conflict if this table is
    # already registered in the current connection.
    con.execute(f"DROP VIEW IF EXISTS {table_name}")

    con.execute(
        f"""
        COPY ({select_sql}) TO '{out_path.as_posix()}'
        (FORMAT PARQUET, COMPRESSION {PARQUET_COMPRESSION.upper()})
        """
    )
    rows = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{out_path.as_posix()}')"
    ).fetchone()[0]
    size_mb = out_path.stat().st_size / 1024 / 1024
    logger.info(f"Wrote {table_name}: {rows:,} rows, {size_mb:.2f} MB → {out_path}")
    return out_path
