from __future__ import annotations

import pandas as pd

from baseball.storage.duckdb_conn import (
    get_connection,
    list_tables,
    register_views,
    table_columns,
)


def test_get_connection_runs_simple_query():
    con = get_connection()
    assert con.execute("SELECT 42").fetchone()[0] == 42


def test_get_connection_applies_memory_limit(monkeypatch):
    from baseball import config

    monkeypatch.setattr(config.settings, "duckdb_memory_limit", "500MB")
    con = get_connection()
    limit = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    # DuckDB normalizes the string (e.g., "500.0 MiB") — just check the magnitude.
    assert "500" in str(limit) or "476" in str(limit)  # 500MB ≈ 476.8 MiB


def test_register_views_without_data_creates_no_pitches_view(isolated_data_root):
    con = get_connection()
    result = register_views(con)
    assert result["pitches"] is False
    assert "pitches" not in list_tables(con)


def test_pitches_view_exposes_hive_partitions(data_root_with_pitches):
    con = get_connection()
    result = register_views(con)
    assert result["pitches"] is True
    assert "pitches" in list_tables(con)

    cols = table_columns(con, "pitches")
    assert "season" in cols
    assert "month" in cols
    assert "pitch_type" in cols


def test_pitches_view_aggregation(data_root_with_pitches):
    con = get_connection()
    register_views(con)
    total = con.execute("SELECT COUNT(*) FROM pitches").fetchone()[0]
    assert total == 4

    by_month = con.execute(
        "SELECT season, month, COUNT(*) AS n FROM pitches GROUP BY season, month ORDER BY month"
    ).fetchdf()
    assert list(by_month["month"]) == [4, 5]
    assert list(by_month["n"]) == [3, 1]


def test_pitches_view_partition_prune_by_season(data_root_with_pitches):
    con = get_connection()
    register_views(con)
    # Filter must compile against season as a real column (via hive partitioning).
    result = con.execute("SELECT COUNT(*) FROM pitches WHERE season = 2024").fetchone()[0]
    assert result == 4
    result = con.execute("SELECT COUNT(*) FROM pitches WHERE season = 2099").fetchone()[0]
    assert result == 0


def test_register_derived_views(isolated_data_root):
    derived_dir = isolated_data_root / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"pitcher": [1, 2], "whiff_rate": [0.25, 0.30]})
    df.to_parquet(derived_dir / "pitcher_pitch_mix.parquet", index=False)

    con = get_connection()
    result = register_views(con)
    assert "pitcher_pitch_mix" in result["derived"]

    out = con.execute("SELECT pitcher, whiff_rate FROM pitcher_pitch_mix ORDER BY pitcher").fetchdf()
    assert list(out["pitcher"]) == [1, 2]
    assert list(out["whiff_rate"]) == [0.25, 0.30]
