"""
App-wide DuckDB connection for the v2 API.

We open one in-memory connection at startup, register all the derived-table
views once, and share it across requests. Each request creates a thread-local
cursor via `con.cursor()` so concurrent SELECTs don't collide.

No persistent database file — views read the latest Parquet on every query,
so the cron's `rebuild-derived` reflects in the API without a restart.
"""

from __future__ import annotations

import duckdb
from fastapi import Depends, HTTPException
from loguru import logger

from baseball.storage.duckdb_conn import get_connection, register_views

_con: duckdb.DuckDBPyConnection | None = None


def init_connection() -> None:
    """Open the app-wide connection and register views. Call once at startup."""
    global _con
    _con = get_connection()
    registered = register_views(_con)
    logger.info(
        f"v2 API connected to DuckDB — pitches view: {registered['pitches']}, "
        f"derived tables: {registered['derived']}, special views: {registered['special']}"
    )


def close_connection() -> None:
    global _con
    if _con is not None:
        _con.close()
        _con = None


def get_cursor() -> duckdb.DuckDBPyConnection:
    """FastAPI dependency: a thread-local cursor sharing the app's schema."""
    if _con is None:
        raise HTTPException(500, detail="DuckDB connection not initialized")
    return _con.cursor()


# Convenience re-export for `Depends(get_cursor)` in route signatures.
CursorDep = Depends(get_cursor)
