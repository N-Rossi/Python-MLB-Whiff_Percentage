from __future__ import annotations

import pandas as pd
import pytest

from baseball.derived.batter_tables import (
    build_batter_swing_decisions,
    build_batter_vs_sequences,
    build_batter_whiff_profile,
)
from baseball.derived.matchup_tables import build_matchup_edges
from baseball.derived.pitcher_tables import (
    build_pitcher_pitch_mix,
    build_pitcher_sequences_2pitch,
    build_pitcher_zone_tendency,
)
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


# ---------------------------------------------------------------------------
# pitcher_zone_tendency
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_pitches_for_zones(isolated_data_root):
    """Two pitchers, mirror-image zone distributions on FF in 0-0.

    Pitcher 100: 8 FF in zone=5, 2 FF in zone=11 (heart-heavy)
    Pitcher 200: 2 FF in zone=5, 8 FF in zone=11 (edge-heavy)

    League for (FF, 0-0):  zone=5: 10, zone=11: 10, total=20
      league_pct(z=5) = league_pct(z=11) = 0.5

    With k=30:
      100/z=5:  (8 + 30*0.5) / (10 + 30) = 23/40 = 0.575
      100/z=11: (2 + 15) / 40 = 17/40 = 0.425
      200/z=5:  (2 + 15) / 40 = 17/40 = 0.425
      200/z=11: (8 + 15) / 40 = 23/40 = 0.575
    """
    rows = []
    for _ in range(8):
        rows.append(_zone_row(100, "A", "FF", 5))
    for _ in range(2):
        rows.append(_zone_row(100, "A", "FF", 11))
    for _ in range(2):
        rows.append(_zone_row(200, "B", "FF", 5))
    for _ in range(8):
        rows.append(_zone_row(200, "B", "FF", 11))
    # NULL zone should be dropped.
    rows.append({**_zone_row(100, "A", "FF", 5), "zone": None})

    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    for col in ("pitcher", "batter", "game_pk", "balls", "strikes", "zone"):
        df[col] = df[col].astype("Int64")

    part = isolated_data_root / "raw" / "statcast" / "season=2024" / "month=04"
    part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "pitches.parquet", compression="zstd", index=False)
    return isolated_data_root


def _zone_row(pitcher: int, name: str, pitch_type: str, zone: int | None) -> dict:
    return {
        "pitcher": pitcher,
        "batter": 999,
        "player_name": name,
        "game_date": "2024-04-01",
        "game_pk": 1,
        "game_type": "R",
        "balls": 0,
        "strikes": 0,
        "pitch_type": pitch_type,
        "zone": zone,
        "p_throws": "R",
    }


def test_pitcher_zone_tendency_row_count(synthetic_pitches_for_zones):
    con = get_connection()
    register_views(con)
    build_pitcher_zone_tendency(con)

    result = pd.read_parquet(
        synthetic_pitches_for_zones / "derived" / "pitcher_zone_tendency.parquet"
    )
    # 4 rows: 2 pitchers × 2 zones each
    assert len(result) == 4


def test_pitcher_zone_tendency_shrinkage_math(synthetic_pitches_for_zones):
    con = get_connection()
    register_views(con)
    build_pitcher_zone_tendency(con)

    r = pd.read_parquet(
        synthetic_pitches_for_zones / "derived" / "pitcher_zone_tendency.parquet"
    ).set_index(["pitcher", "zone"])

    # Mirror-image shrinkage:
    assert r.loc[(100, 5), "pct_raw"] == pytest.approx(0.8)
    assert r.loc[(100, 5), "pct_shrunk"] == pytest.approx(0.575)
    assert r.loc[(200, 5), "pct_shrunk"] == pytest.approx(0.425)
    assert r.loc[(100, 11), "pct_shrunk"] == pytest.approx(0.425)
    assert r.loc[(200, 11), "pct_shrunk"] == pytest.approx(0.575)


# ---------------------------------------------------------------------------
# pitcher_sequences_2pitch
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_pitches_for_sequences(isolated_data_root):
    """Craft four plate appearances with known 2-pitch sequences.

    Pitcher 100 (Ace) throws FF→CH at (0,1) four times:
      PA1: FF(0-1) → CH(0-2, swinging_strike, strikeout)   # whiff + put_away
      PA2: FF(0-1) → CH(0-2, foul)                         # swing, not whiff
      PA3: FF(0-1) → CH(0-2, swinging_strike, strikeout)   # whiff + put_away
      PA4: FF(0-1) → CH(0-2, called_strike)                # no swing
    Pitcher 100 aggregate (FF→CH @ 0-1):
      n=4, swings=3, whiffs=2, two_strike_p2=4, put_aways=2
      whiff_rate_raw = 2/3 ≈ 0.6667
      put_away_rate_raw = 2/4 = 0.5

    Pitcher 200 (Avg) throws FF→CH at (0,1) twice:
      PA5: FF(0-1) → CH(0-2, ball)               # no swing
      PA6: FF(0-1) → CH(0-2, hit_into_play)      # swing, not whiff
    Pitcher 200 aggregate:
      n=2, swings=1, whiffs=0, two_strike_p2=2, put_aways=0
      whiff_rate_raw = 0/1 = 0.0
      put_away_rate_raw = 0/2 = 0.0

    League FF→CH @ (0,1):
      n=6, swings=4, whiffs=2, two_strike=6, put_aways=2
      league_whiff_rate = 2/4 = 0.5
      league_put_away_rate = 2/6 ≈ 0.3333

    Expected shrunk (k_whiff=50, k_pa=40):
      Pitcher 100 whiff_rate_shrunk = (2 + 50*0.5) / (3 + 50) = 27/53 ≈ 0.5094
      Pitcher 100 put_away_rate_shrunk = (2 + 40*0.3333) / (4 + 40) = 15.333/44 ≈ 0.3485
    """
    rows = []
    pa_id = 0
    for outcome in [
        ("swinging_strike", "strikeout"),
        ("foul", None),
        ("swinging_strike", "strikeout"),
        ("called_strike", None),
    ]:
        pa_id += 1
        rows.append(_seq_row(100, "Ace", pa_id, 1, "FF", 0, 1, "called_strike", None))
        rows.append(_seq_row(100, "Ace", pa_id, 2, "CH", 0, 2, *outcome))

    for outcome in [("ball", None), ("hit_into_play", None)]:
        pa_id += 1
        rows.append(_seq_row(200, "Avg", pa_id, 1, "FF", 0, 1, "called_strike", None))
        rows.append(_seq_row(200, "Avg", pa_id, 2, "CH", 0, 2, *outcome))

    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    for col in ("pitcher", "batter", "game_pk", "at_bat_number", "pitch_number",
                "balls", "strikes"):
        df[col] = df[col].astype("Int64")

    part = isolated_data_root / "raw" / "statcast" / "season=2024" / "month=04"
    part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "pitches.parquet", compression="zstd", index=False)
    return isolated_data_root


def _seq_row(
    pitcher: int, name: str, ab: int, pn: int, pitch_type: str,
    balls: int, strikes: int, description: str, events: str | None,
) -> dict:
    return {
        "pitcher": pitcher,
        "batter": 999,
        "player_name": name,
        "game_date": "2024-04-01",
        "game_pk": 1,
        "at_bat_number": ab,
        "pitch_number": pn,
        "game_type": "R",
        "pitch_type": pitch_type,
        "balls": balls,
        "strikes": strikes,
        "description": description,
        "events": events,
        "p_throws": "R",
    }


def test_sequences_row_count_and_keys(synthetic_pitches_for_sequences):
    con = get_connection()
    register_views(con)
    build_pitcher_sequences_2pitch(con)

    r = pd.read_parquet(
        synthetic_pitches_for_sequences / "derived" / "pitcher_sequences_2pitch.parquet"
    )
    # 2 rows: (100, FF→CH @ 0-1) and (200, FF→CH @ 0-1)
    assert len(r) == 2
    assert set(r["pitch1_type"]) == {"FF"}
    assert set(r["pitch2_type"]) == {"CH"}
    assert set(r["balls_before_p1"]) == {0}
    assert set(r["strikes_before_p1"]) == {1}


def test_sequences_counts_for_ace(synthetic_pitches_for_sequences):
    con = get_connection()
    register_views(con)
    build_pitcher_sequences_2pitch(con)

    r = pd.read_parquet(
        synthetic_pitches_for_sequences / "derived" / "pitcher_sequences_2pitch.parquet"
    ).set_index("pitcher")

    assert r.loc[100, "n_sequences"] == 4
    assert r.loc[100, "swings_on_p2"] == 3
    assert r.loc[100, "whiffs_on_p2"] == 2
    assert r.loc[100, "two_strike_p2"] == 4
    assert r.loc[100, "put_aways"] == 2
    assert r.loc[100, "whiff_rate_raw"] == pytest.approx(2 / 3)
    assert r.loc[100, "put_away_rate_raw"] == pytest.approx(0.5)


def test_sequences_league_rates(synthetic_pitches_for_sequences):
    con = get_connection()
    register_views(con)
    build_pitcher_sequences_2pitch(con)

    r = pd.read_parquet(
        synthetic_pitches_for_sequences / "derived" / "pitcher_sequences_2pitch.parquet"
    )
    # League rates are identical across rows with same sequence key.
    whiff_uniq = r["league_whiff_rate"].unique()
    pa_uniq = r["league_put_away_rate"].unique()
    assert len(whiff_uniq) == 1 and whiff_uniq[0] == pytest.approx(0.5)
    assert len(pa_uniq) == 1 and pa_uniq[0] == pytest.approx(2 / 6)


def test_sequences_shrinkage_hand_computed(synthetic_pitches_for_sequences):
    con = get_connection()
    register_views(con)
    build_pitcher_sequences_2pitch(con)

    r = pd.read_parquet(
        synthetic_pitches_for_sequences / "derived" / "pitcher_sequences_2pitch.parquet"
    ).set_index("pitcher")

    # whiff_rate_shrunk (k=50): (2 + 50*0.5) / (3 + 50) = 27/53
    assert r.loc[100, "whiff_rate_shrunk"] == pytest.approx(27 / 53)
    # put_away_rate_shrunk (k=40): (2 + 40*(2/6)) / (4 + 40) = (2 + 40/3) / 44
    expected_pa = (2 + 40 * (2 / 6)) / 44
    assert r.loc[100, "put_away_rate_shrunk"] == pytest.approx(expected_pa)


def test_sequences_lag_does_not_cross_plate_appearances(isolated_data_root):
    """Ensure LAG window is scoped to (game_pk, at_bat_number). A pitch at the
    start of PA 2 must NOT see the last pitch of PA 1 as its predecessor."""
    rows = [
        # PA 1: single pitch
        _seq_row(100, "A", 1, 1, "FF", 0, 0, "called_strike", None),
        # PA 2: single pitch — must not chain off the FF from PA 1
        _seq_row(100, "A", 2, 1, "SL", 0, 0, "ball", None),
    ]
    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    for col in ("pitcher", "batter", "game_pk", "at_bat_number", "pitch_number",
                "balls", "strikes"):
        df[col] = df[col].astype("Int64")

    part = isolated_data_root / "raw" / "statcast" / "season=2024" / "month=04"
    part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "pitches.parquet", compression="zstd", index=False)

    con = get_connection()
    register_views(con)
    build_pitcher_sequences_2pitch(con)

    r = pd.read_parquet(
        isolated_data_root / "derived" / "pitcher_sequences_2pitch.parquet"
    )
    # No sequences should be produced: each PA had only one pitch.
    assert len(r) == 0


# ---------------------------------------------------------------------------
# batter_whiff_profile
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_pitches_for_whiff_profile(isolated_data_root):
    """Batter 100: 3 whiffs / 5 contact = 8 swings total at FF/zone=5/0-0.
    Batter 200: 3 whiffs / 1 contact = 4 swings total at FF/zone=5/0-0.
    League: 6 whiffs / 12 swings → league_whiff_rate = 0.5.

    Expected (k=50):
      100: raw = 3/8 = 0.375,  shrunk = (3 + 25)/58 = 28/58
      200: raw = 3/4 = 0.75,   shrunk = (3 + 25)/54 = 28/54
    """
    rows = []
    for _ in range(3):
        rows.append(_whiff_row(100, "FF", 5, "swinging_strike"))
    for _ in range(5):
        rows.append(_whiff_row(100, "FF", 5, "foul"))
    for _ in range(3):
        rows.append(_whiff_row(200, "FF", 5, "swinging_strike"))
    for _ in range(1):
        rows.append(_whiff_row(200, "FF", 5, "foul"))
    # Non-swing (should be ignored for whiff_profile)
    rows.append(_whiff_row(100, "FF", 5, "ball"))

    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    for col in ("pitcher", "batter", "game_pk", "balls", "strikes", "zone"):
        df[col] = df[col].astype("Int64")

    part = isolated_data_root / "raw" / "statcast" / "season=2024" / "month=04"
    part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "pitches.parquet", compression="zstd", index=False)
    return isolated_data_root


def _whiff_row(batter: int, pitch_type: str, zone: int, description: str) -> dict:
    return {
        "pitcher": 999,
        "batter": batter,
        "player_name": "p",
        "game_date": "2024-04-01",
        "game_pk": 1,
        "game_type": "R",
        "balls": 0,
        "strikes": 0,
        "pitch_type": pitch_type,
        "zone": zone,
        "description": description,
        "p_throws": "R",
    }


def test_batter_whiff_profile_ignores_non_swings(synthetic_pitches_for_whiff_profile):
    con = get_connection()
    register_views(con)
    build_batter_whiff_profile(con)

    r = pd.read_parquet(
        synthetic_pitches_for_whiff_profile / "derived" / "batter_whiff_profile.parquet"
    ).set_index("batter")
    assert r.loc[100, "swings"] == 8       # not 9 — the 'ball' row excluded
    assert r.loc[200, "swings"] == 4


def test_batter_whiff_profile_rates(synthetic_pitches_for_whiff_profile):
    con = get_connection()
    register_views(con)
    build_batter_whiff_profile(con)

    r = pd.read_parquet(
        synthetic_pitches_for_whiff_profile / "derived" / "batter_whiff_profile.parquet"
    ).set_index("batter")

    assert r.loc[100, "whiff_rate_raw"] == pytest.approx(3 / 8)
    assert r.loc[200, "whiff_rate_raw"] == pytest.approx(3 / 4)
    assert r.loc[100, "league_whiff_rate"] == pytest.approx(0.5)
    assert r.loc[100, "whiff_rate_shrunk"] == pytest.approx(28 / 58)
    assert r.loc[200, "whiff_rate_shrunk"] == pytest.approx(28 / 54)


# ---------------------------------------------------------------------------
# batter_swing_decisions
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_pitches_for_swing_decisions(isolated_data_root):
    """All pitches are 0-0 count.

    Batter 100:
      zone=5  ×6 pitches: 3 swings (foul) + 3 takes (called_strike)
      zone=11 ×4 pitches: 1 swing (foul) + 3 takes (ball)
    Batter 200:
      zone=5  ×4 pitches: 3 swings (foul) + 1 take (called_strike)
      zone=11 ×6 pitches: 3 swings (foul) + 3 takes (ball)

    League 0-0 totals: 10 in-zone (6 swings), 10 oz (4 swings)
      league_z_swing_rate = 0.6, league_chase_rate = 0.4

    Expected (k=50):
      100: z_swing_raw = 3/6 = 0.5,  shrunk = (3 + 30)/56 = 33/56
           chase_raw   = 1/4 = 0.25, shrunk = (1 + 20)/54 = 21/54
      200: z_swing_raw = 3/4 = 0.75, shrunk = (3 + 30)/54 = 33/54
           chase_raw   = 3/6 = 0.5,  shrunk = (3 + 20)/56 = 23/56
    """
    rows = []
    # Batter 100
    for _ in range(3):
        rows.append(_swing_row(100, 5, "foul"))
    for _ in range(3):
        rows.append(_swing_row(100, 5, "called_strike"))
    for _ in range(1):
        rows.append(_swing_row(100, 11, "foul"))
    for _ in range(3):
        rows.append(_swing_row(100, 11, "ball"))
    # Batter 200
    for _ in range(3):
        rows.append(_swing_row(200, 5, "foul"))
    for _ in range(1):
        rows.append(_swing_row(200, 5, "called_strike"))
    for _ in range(3):
        rows.append(_swing_row(200, 11, "foul"))
    for _ in range(3):
        rows.append(_swing_row(200, 11, "ball"))

    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    for col in ("pitcher", "batter", "game_pk", "balls", "strikes", "zone"):
        df[col] = df[col].astype("Int64")

    part = isolated_data_root / "raw" / "statcast" / "season=2024" / "month=04"
    part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "pitches.parquet", compression="zstd", index=False)
    return isolated_data_root


def _swing_row(batter: int, zone: int, description: str) -> dict:
    return {
        "pitcher": 999,
        "batter": batter,
        "player_name": "p",
        "game_date": "2024-04-01",
        "game_pk": 1,
        "game_type": "R",
        "balls": 0,
        "strikes": 0,
        "pitch_type": "FF",
        "zone": zone,
        "description": description,
        "p_throws": "R",
    }


def test_swing_decisions_counts(synthetic_pitches_for_swing_decisions):
    con = get_connection()
    register_views(con)
    build_batter_swing_decisions(con)

    r = pd.read_parquet(
        synthetic_pitches_for_swing_decisions / "derived" / "batter_swing_decisions.parquet"
    ).set_index("batter")
    assert r.loc[100, "pitches_in_zone"] == 6
    assert r.loc[100, "pitches_out_of_zone"] == 4
    assert r.loc[100, "swings_in_zone"] == 3
    assert r.loc[100, "swings_out_of_zone"] == 1


def test_swing_decisions_raw_and_league_rates(synthetic_pitches_for_swing_decisions):
    con = get_connection()
    register_views(con)
    build_batter_swing_decisions(con)

    r = pd.read_parquet(
        synthetic_pitches_for_swing_decisions / "derived" / "batter_swing_decisions.parquet"
    ).set_index("batter")

    assert r.loc[100, "z_swing_rate_raw"] == pytest.approx(0.5)
    assert r.loc[100, "chase_rate_raw"] == pytest.approx(0.25)
    assert r.loc[200, "z_swing_rate_raw"] == pytest.approx(0.75)
    assert r.loc[200, "chase_rate_raw"] == pytest.approx(0.5)
    assert r.loc[100, "league_z_swing_rate"] == pytest.approx(0.6)
    assert r.loc[100, "league_chase_rate"] == pytest.approx(0.4)


def test_swing_decisions_shrinkage(synthetic_pitches_for_swing_decisions):
    con = get_connection()
    register_views(con)
    build_batter_swing_decisions(con)

    r = pd.read_parquet(
        synthetic_pitches_for_swing_decisions / "derived" / "batter_swing_decisions.parquet"
    ).set_index("batter")

    # k=50 for both metrics
    assert r.loc[100, "z_swing_rate_shrunk"] == pytest.approx(33 / 56)
    assert r.loc[100, "chase_rate_shrunk"] == pytest.approx(21 / 54)
    assert r.loc[200, "z_swing_rate_shrunk"] == pytest.approx(33 / 54)
    assert r.loc[200, "chase_rate_shrunk"] == pytest.approx(23 / 56)


# ---------------------------------------------------------------------------
# batter_vs_sequences
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_pitches_for_batter_seq(isolated_data_root):
    """5 PAs of FF→SL across two batters.

    Batter 100:
      PA 1: FF(0-0, ball)          → SL(1-0, swinging_strike)        # whiff, not 2-strike
      PA 2: FF(0-1, foul)          → SL(0-2, foul)                   # swing, 2-strike, no K
      PA 3: FF(0-1, called_strike) → SL(0-2, swinging_strike, K)     # whiff, 2-strike, K
    Batter 200:
      PA 4: FF(0-0, called_strike) → SL(0-1, ball)                   # no swing, not 2-strike
      PA 5: FF(0-1, called_strike) → SL(0-2, hit_into_play)          # swing, 2-strike, no K

    Aggregates:
      Batter 100: n=3, swings=3, whiffs=2, two_strike_p2=2, K=1
                  whiff_raw=2/3, strikeout_raw=1/2
      Batter 200: n=2, swings=1, whiffs=0, two_strike_p2=1, K=0
                  whiff_raw=0,   strikeout_raw=0
      League:     n=5, swings=4, whiffs=2, two_strike=3, K=1
                  league_whiff=0.5, league_strikeout=1/3

    Expected shrunk (k_whiff=50, k_K=40):
      Batter 100 whiff_shrunk = (2 + 25)/53 = 27/53
      Batter 100 strikeout_shrunk = (1 + 40/3)/42
    """
    rows = []
    # PA 1
    rows.append(_pa_row(100, 1, 1, "FF", 0, 0, "ball", None))
    rows.append(_pa_row(100, 1, 2, "SL", 1, 0, "swinging_strike", None))
    # PA 2
    rows.append(_pa_row(100, 2, 1, "FF", 0, 1, "foul", None))
    rows.append(_pa_row(100, 2, 2, "SL", 0, 2, "foul", None))
    # PA 3
    rows.append(_pa_row(100, 3, 1, "FF", 0, 1, "called_strike", None))
    rows.append(_pa_row(100, 3, 2, "SL", 0, 2, "swinging_strike", "strikeout"))
    # PA 4
    rows.append(_pa_row(200, 4, 1, "FF", 0, 0, "called_strike", None))
    rows.append(_pa_row(200, 4, 2, "SL", 0, 1, "ball", None))
    # PA 5
    rows.append(_pa_row(200, 5, 1, "FF", 0, 1, "called_strike", None))
    rows.append(_pa_row(200, 5, 2, "SL", 0, 2, "hit_into_play", None))

    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    for col in ("pitcher", "batter", "game_pk", "at_bat_number", "pitch_number",
                "balls", "strikes"):
        df[col] = df[col].astype("Int64")

    part = isolated_data_root / "raw" / "statcast" / "season=2024" / "month=04"
    part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "pitches.parquet", compression="zstd", index=False)
    return isolated_data_root


def _pa_row(
    batter: int, ab: int, pn: int, pitch_type: str,
    balls: int, strikes: int, description: str, events: str | None,
) -> dict:
    return {
        "pitcher": 999,
        "batter": batter,
        "player_name": "p",
        "game_date": "2024-04-01",
        "game_pk": 1,
        "at_bat_number": ab,
        "pitch_number": pn,
        "game_type": "R",
        "pitch_type": pitch_type,
        "balls": balls,
        "strikes": strikes,
        "description": description,
        "events": events,
        "p_throws": "R",
    }


def test_batter_vs_sequences_aggregates(synthetic_pitches_for_batter_seq):
    con = get_connection()
    register_views(con)
    build_batter_vs_sequences(con)

    r = pd.read_parquet(
        synthetic_pitches_for_batter_seq / "derived" / "batter_vs_sequences.parquet"
    ).set_index("batter")

    assert r.loc[100, "n_sequences"] == 3
    assert r.loc[100, "swings_on_p2"] == 3
    assert r.loc[100, "whiffs_on_p2"] == 2
    assert r.loc[100, "two_strike_p2"] == 2
    assert r.loc[100, "strikeouts_on_p2"] == 1

    assert r.loc[200, "n_sequences"] == 2
    assert r.loc[200, "swings_on_p2"] == 1
    assert r.loc[200, "two_strike_p2"] == 1


def test_batter_vs_sequences_rates(synthetic_pitches_for_batter_seq):
    con = get_connection()
    register_views(con)
    build_batter_vs_sequences(con)

    r = pd.read_parquet(
        synthetic_pitches_for_batter_seq / "derived" / "batter_vs_sequences.parquet"
    ).set_index("batter")

    assert r.loc[100, "whiff_rate_raw"] == pytest.approx(2 / 3)
    assert r.loc[100, "strikeout_rate_raw"] == pytest.approx(0.5)
    assert r.loc[100, "whiff_rate_shrunk"] == pytest.approx(27 / 53)
    # strikeout_rate_shrunk = (1 + 40*(1/3)) / (2 + 40)
    expected_k = (1 + 40 * (1 / 3)) / 42
    assert r.loc[100, "strikeout_rate_shrunk"] == pytest.approx(expected_k)


# ---------------------------------------------------------------------------
# matchup_edges
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_pitches_for_matchup(isolated_data_root):
    """Build a minimal but complete scenario where matchup edge math is tractable.

    Pitcher 100 ('A') throws in 0-0:  20 FF + 20 SL  (pct_shrunk FF ≈ SL)
    Pitcher 200 ('B') throws in 0-0:  40 FF          (pct_shrunk FF ≈ 1.0)

    Batter 900 faces both pitchers. In 0-0:
      - swings at 10 FF (3 whiffs)
      - swings at 10 SL (6 whiffs)  → high SL vulnerability
    Batter 901 faces both pitchers. In 0-0:
      - swings at 10 FF (3 whiffs)
      - swings at 10 SL (3 whiffs)

    The whiff-profile swings are shared across batters — I realize the math
    cross-dimension, so the test focuses on *shape* (rows exist, joins work,
    edge_weighted == pitcher_pct_shrunk * edge_lift) rather than exact values.
    """
    rows = []
    for i in range(20):
        rows.append(_match_row(100, 900 + (i % 2), "FF", 5, "foul"))
    for i in range(20):
        rows.append(_match_row(100, 900 + (i % 2), "SL", 5,
                               "swinging_strike" if i < 9 else "foul"))
    for i in range(40):
        rows.append(_match_row(200, 900 + (i % 2), "FF", 5,
                               "swinging_strike" if i < 6 else "foul"))

    df = pd.DataFrame(rows)
    df["game_date"] = pd.to_datetime(df["game_date"])
    for col in ("pitcher", "batter", "game_pk", "balls", "strikes", "zone"):
        df[col] = df[col].astype("Int64")

    part = isolated_data_root / "raw" / "statcast" / "season=2024" / "month=04"
    part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "pitches.parquet", compression="zstd", index=False)
    return isolated_data_root


def _match_row(pitcher: int, batter: int, pitch_type: str, zone: int, description: str) -> dict:
    return {
        "pitcher": pitcher,
        "batter": batter,
        "player_name": f"P{pitcher}",
        "game_date": "2024-04-01",
        "game_pk": 1,
        "game_type": "R",
        "balls": 0,
        "strikes": 0,
        "pitch_type": pitch_type,
        "zone": zone,
        "description": description,
        "p_throws": "R",
    }


def _build_matchup_prerequisites(synthetic_pitches_for_matchup):
    con = get_connection()
    register_views(con)
    build_pitcher_pitch_mix(con)
    build_batter_whiff_profile(con)
    build_matchup_edges(con)
    return con


def test_matchup_edges_produces_rows_and_right_keys(synthetic_pitches_for_matchup):
    _build_matchup_prerequisites(synthetic_pitches_for_matchup)

    r = pd.read_parquet(
        synthetic_pitches_for_matchup / "derived" / "matchup_edges.parquet"
    )
    # Pairs × cells-in-common:
    #   (100, 900), (100, 901): both have FF and SL cells from pitcher
    #     and both have FF and SL cells from batter → 2 cells each → 4 rows
    #   (200, 900), (200, 901): only FF cell from pitcher
    #     and both batters have FF cells → 1 cell each → 2 rows
    # Total: 6 rows
    assert len(r) == 6
    assert set(r["pitcher"]) == {100, 200}
    assert set(r["batter"]) == {900, 901}


def test_matchup_edge_weighted_equals_pct_shrunk_times_lift(synthetic_pitches_for_matchup):
    _build_matchup_prerequisites(synthetic_pitches_for_matchup)
    r = pd.read_parquet(
        synthetic_pitches_for_matchup / "derived" / "matchup_edges.parquet"
    )
    # edge_weighted should exactly equal pitcher_pct_shrunk * edge_lift
    assert ((r["edge_weighted"] - r["pitcher_pct_shrunk"] * r["edge_lift"]).abs()
            < 1e-12).all()


def test_matchup_edges_missing_prereq_raises(isolated_data_root):
    """Calling build_matchup_edges without prerequisites on disk should error cleanly."""
    con = get_connection()
    # No raw pitches, no derived tables
    with pytest.raises(FileNotFoundError, match="matchup_edges needs"):
        build_matchup_edges(con)


def test_matchup_edges_top_view_registered(synthetic_pitches_for_matchup):
    _build_matchup_prerequisites(synthetic_pitches_for_matchup)
    # After building, a fresh session should get the summary view.
    con = get_connection()
    register_views(con)
    # Use the DB directly — bypass list_tables because it doesn't pull views
    # from all schemas by default. DESCRIBE works for both.
    result = con.execute("SELECT COUNT(*) FROM matchup_edges_top").fetchone()[0]
    # One row per (pitcher, batter, season): 4 pairs
    assert result == 4
