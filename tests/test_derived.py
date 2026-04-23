from __future__ import annotations

import pandas as pd
import pytest

from baseball.derived.pitcher_tables import build_pitcher_pitch_mix
from baseball.jobs.rebuild_derived import REGISTRY, rebuild_one
from baseball.storage.duckdb_conn import get_connection, register_views


@pytest.fixture
def synthetic_pitches_for_mix(isolated_data_root):
    """Build a tiny fixture where pitch_mix shrinkage math is tractable by hand.

    All rows are regular season, 0-0 count. Plus one spring-training row we
    expect the filter to drop.

    Pitcher 100 ('A'): 10 FF + 10 SL   → n=20
    Pitcher 200 ('B'):       20 SL     → n=20 (no FF)

    League totals in 0-0: 10 FF + 30 SL = 40
      league_pct(FF|0-0) = 10/40 = 0.25
      league_pct(SL|0-0) = 30/40 = 0.75

    With k=20, expected shrunk values:
      100/FF: (10 + 20*0.25) / (20+20) = 15/40 = 0.375
      100/SL: (10 + 20*0.75) / (20+20) = 25/40 = 0.625
      200/SL: (20 + 20*0.75) / (20+20) = 35/40 = 0.875
    """
    rows = []
    for _ in range(10):
        rows.append(_row(100, "A", "FF", "R"))
    for _ in range(10):
        rows.append(_row(100, "A", "SL", "R"))
    for _ in range(20):
        rows.append(_row(200, "B", "SL", "R"))
    rows.append(_row(100, "A", "CU", "S"))  # spring training — should be filtered

    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    for col in ("pitcher", "batter", "game_pk", "balls", "strikes"):
        df[col] = df[col].astype("Int64")

    part = isolated_data_root / "raw" / "statcast" / "season=2024" / "month=04"
    part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "pitches.parquet", compression="zstd", index=False)
    return isolated_data_root


def _row(pitcher: int, name: str, pitch_type: str, game_type: str) -> dict:
    return {
        "pitcher": pitcher,
        "batter": 999,
        "player_name": name,
        "game_date": "2024-04-01",
        "game_pk": 1,
        "game_type": game_type,
        "balls": 0,
        "strikes": 0,
        "pitch_type": pitch_type,
        "p_throws": "R",
    }


def test_pitcher_pitch_mix_row_count_and_filter(synthetic_pitches_for_mix):
    con = get_connection()
    register_views(con)
    build_pitcher_pitch_mix(con)

    result = pd.read_parquet(
        synthetic_pitches_for_mix / "derived" / "pitcher_pitch_mix.parquet"
    )
    # Expected 3 rows: (100,FF), (100,SL), (200,SL). The spring training CU is filtered.
    assert len(result) == 3
    assert "CU" not in result["pitch_type"].values


def test_pitcher_pitch_mix_league_pct_is_identical_across_rows(synthetic_pitches_for_mix):
    con = get_connection()
    register_views(con)
    build_pitcher_pitch_mix(con)

    result = pd.read_parquet(
        synthetic_pitches_for_mix / "derived" / "pitcher_pitch_mix.parquet"
    )
    ff_league = result[result["pitch_type"] == "FF"]["league_pct"].unique()
    sl_league = result[result["pitch_type"] == "SL"]["league_pct"].unique()
    assert len(ff_league) == 1 and ff_league[0] == pytest.approx(0.25)
    assert len(sl_league) == 1 and sl_league[0] == pytest.approx(0.75)


def test_pitcher_pitch_mix_raw_rates(synthetic_pitches_for_mix):
    con = get_connection()
    register_views(con)
    build_pitcher_pitch_mix(con)

    r = pd.read_parquet(
        synthetic_pitches_for_mix / "derived" / "pitcher_pitch_mix.parquet"
    ).set_index(["pitcher", "pitch_type"])

    assert r.loc[(100, "FF"), "pitch_count"] == 10
    assert r.loc[(100, "FF"), "total_in_count"] == 20
    assert r.loc[(100, "FF"), "pct_raw"] == pytest.approx(0.5)
    assert r.loc[(100, "SL"), "pct_raw"] == pytest.approx(0.5)
    assert r.loc[(200, "SL"), "pct_raw"] == pytest.approx(1.0)


def test_pitcher_pitch_mix_shrinkage_hand_computed(synthetic_pitches_for_mix):
    con = get_connection()
    register_views(con)
    build_pitcher_pitch_mix(con)

    r = pd.read_parquet(
        synthetic_pitches_for_mix / "derived" / "pitcher_pitch_mix.parquet"
    ).set_index(["pitcher", "pitch_type"])

    # See docstring on the fixture for the math.
    assert r.loc[(100, "FF"), "pct_shrunk"] == pytest.approx(0.375)
    assert r.loc[(100, "SL"), "pct_shrunk"] == pytest.approx(0.625)
    assert r.loc[(200, "SL"), "pct_shrunk"] == pytest.approx(0.875)


def test_pitcher_pitch_mix_shrinkage_moves_toward_league(synthetic_pitches_for_mix):
    con = get_connection()
    register_views(con)
    build_pitcher_pitch_mix(con)

    r = pd.read_parquet(
        synthetic_pitches_for_mix / "derived" / "pitcher_pitch_mix.parquet"
    )
    # For every row, pct_shrunk must lie between pct_raw and league_pct (inclusive).
    lo = r[["pct_raw", "league_pct"]].min(axis=1)
    hi = r[["pct_raw", "league_pct"]].max(axis=1)
    assert ((r["pct_shrunk"] >= lo - 1e-9) & (r["pct_shrunk"] <= hi + 1e-9)).all()


def test_rebuild_derived_registry_contains_pitcher_pitch_mix():
    assert "pitcher_pitch_mix" in REGISTRY


def test_rebuild_one_unknown_table_raises():
    with pytest.raises(ValueError, match="Unknown derived table"):
        rebuild_one("does_not_exist")


def test_rebuild_derived_cli_unknown_table(data_root_with_pitches):
    from typer.testing import CliRunner

    from baseball.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["rebuild-derived", "--table", "does_not_exist"])
    assert result.exit_code != 0
    assert "Unknown table" in result.output
