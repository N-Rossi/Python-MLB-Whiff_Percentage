"""Pitcher-centric derived tables."""

from __future__ import annotations

import duckdb
from loguru import logger

from baseball.config import SHRINKAGE_K
from baseball.derived._common import write_derived_parquet


def build_pitcher_pitch_mix(con: duckdb.DuckDBPyConnection) -> None:
    """pitcher_pitch_mix — pitch-type frequency by (pitcher, season, balls, strikes, pitch_type).

    Scope: regular season only (game_type = 'R'). Spring training and
    postseason are excluded because they have materially different
    pitch-selection contexts; a separate view can expose them later.

    Rate columns:
      pct_raw     = pitch_count / total_in_count
      pct_shrunk  = empirical-Bayes shrunk toward `league_pct`:
                      (pitch_count + k * league_pct) / (total_in_count + k)

    Shrinkage strength `k` is config.SHRINKAGE_K["pitch_mix"].
    """
    k = SHRINKAGE_K["pitch_mix"]
    logger.info(f"Building pitcher_pitch_mix (shrinkage k={k})")

    sql = f"""
        WITH regular AS (
            SELECT
                pitcher,
                player_name,
                season,
                CAST(balls AS SMALLINT) AS balls,
                CAST(strikes AS SMALLINT) AS strikes,
                pitch_type
            FROM pitches
            WHERE game_type = 'R'
              AND pitch_type IS NOT NULL
              AND pitcher IS NOT NULL
              AND balls BETWEEN 0 AND 3
              AND strikes BETWEEN 0 AND 2
        ),
        pitcher_count_agg AS (
            SELECT pitcher, season, balls, strikes, pitch_type, COUNT(*) AS pitch_count
            FROM regular
            GROUP BY 1, 2, 3, 4, 5
        ),
        pitcher_count_totals AS (
            SELECT pitcher, season, balls, strikes, SUM(pitch_count) AS total_in_count
            FROM pitcher_count_agg
            GROUP BY 1, 2, 3, 4
        ),
        league_count_agg AS (
            SELECT season, balls, strikes, pitch_type, COUNT(*) AS league_pitch_count
            FROM regular
            GROUP BY 1, 2, 3, 4
        ),
        league_count_totals AS (
            SELECT season, balls, strikes, SUM(league_pitch_count) AS league_total_in_count
            FROM league_count_agg
            GROUP BY 1, 2, 3
        ),
        names AS (
            SELECT pitcher, season, ANY_VALUE(player_name) AS player_name
            FROM regular
            GROUP BY 1, 2
        )
        SELECT
            pc.pitcher,
            n.player_name,
            pc.season,
            pc.balls,
            pc.strikes,
            pc.pitch_type,
            pc.pitch_count,
            pct.total_in_count,
            (lca.league_pitch_count * 1.0 / lct.league_total_in_count) AS league_pct,
            (pc.pitch_count * 1.0 / pct.total_in_count) AS pct_raw,
            (pc.pitch_count
                + {k} * (lca.league_pitch_count * 1.0 / lct.league_total_in_count))
                / (pct.total_in_count + {k}) AS pct_shrunk
        FROM pitcher_count_agg pc
        JOIN pitcher_count_totals pct USING (pitcher, season, balls, strikes)
        JOIN league_count_agg lca USING (season, balls, strikes, pitch_type)
        JOIN league_count_totals lct USING (season, balls, strikes)
        JOIN names n USING (pitcher, season)
        ORDER BY season, pitcher, balls, strikes, pitch_type
    """
    write_derived_parquet(con, sql, "pitcher_pitch_mix")
