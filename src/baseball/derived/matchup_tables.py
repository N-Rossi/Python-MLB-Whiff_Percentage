"""Cross-joined matchup tables: pitcher tendency × batter vulnerability."""

from __future__ import annotations

import duckdb
from loguru import logger

from baseball.config import SHRINKAGE_K, settings
from baseball.derived._common import write_derived_parquet

REQUIRED_INPUTS: tuple[str, ...] = ("pitcher_pitch_mix", "batter_whiff_profile")


def _ensure_inputs_registered(con: duckdb.DuckDBPyConnection) -> None:
    """Make sure the required upstream derived tables exist on disk and are
    registered as views in this connection. Raises FileNotFoundError with a
    remediation hint if any prerequisite is missing."""
    for name in REQUIRED_INPUTS:
        path = settings.derived_dir / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"matchup_edges needs {name} built first. "
                f"Run `baseball rebuild-derived` (all tables in order) or "
                f"`baseball rebuild-derived --table {name}` followed by this one."
            )
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{path.as_posix()}')"
        )


def build_matchup_edges(con: duckdb.DuckDBPyConnection) -> None:
    """matchup_edges — one row per (pitcher, batter, season, pitch_type, balls, strikes).

    The row exists iff:
      - the pitcher has thrown this pitch_type in this count at least once
        in the season (there's a row in `pitcher_pitch_mix`), AND
      - the batter has swung at this pitch_type in this count at least once
        in the season (there are rows in `batter_whiff_profile`), AND
      - the pitcher actually faced this batter in this season (any pitch).

    Each row carries both sides' sample sizes plus three edge metrics:
      batter_whiff_shrunk — batter's whiff rate on (pitch_type, count),
                            shrunk toward league (k=50). Zones are rolled up.
      edge_lift           — batter_whiff_shrunk - league_whiff_rate.
                            Positive = batter more vulnerable than average.
      edge_weighted       — pitcher_pct_shrunk * edge_lift.
                            The "leverage" — only useful if the pitcher
                            actually throws this pitch often.

    A convenience wrapper view `matchup_edges_top` (registered by
    `storage.duckdb_conn.register_views`) gives the top-3 edges per
    (pitcher, batter, season).
    """
    _ensure_inputs_registered(con)

    k = SHRINKAGE_K["whiff_profile"]
    logger.info(f"Building matchup_edges (shrinkage k={k})")

    sql = f"""
        WITH pairs AS (
            SELECT DISTINCT pitcher, batter, season
            FROM pitches
            WHERE game_type = 'R'
              AND pitcher IS NOT NULL
              AND batter IS NOT NULL
        ),
        batter_rollup AS (
            SELECT
                batter, season, pitch_type,
                CAST(balls AS SMALLINT) AS balls,
                CAST(strikes AS SMALLINT) AS strikes,
                SUM(swings) AS batter_swings,
                SUM(whiffs) AS batter_whiffs
            FROM batter_whiff_profile
            GROUP BY 1, 2, 3, 4, 5
        ),
        league AS (
            SELECT
                season, pitch_type,
                CAST(balls AS SMALLINT) AS balls,
                CAST(strikes AS SMALLINT) AS strikes,
                SUM(swings) AS league_swings,
                SUM(whiffs) AS league_whiffs,
                SUM(whiffs) * 1.0 / NULLIF(SUM(swings), 0) AS league_whiff_rate
            FROM batter_whiff_profile
            GROUP BY 1, 2, 3, 4
        )
        SELECT
            pm.pitcher,
            pm.player_name,
            pairs.batter,
            pm.season,
            pm.pitch_type,
            pm.balls,
            pm.strikes,
            pm.pitch_count AS pitcher_n,
            pm.total_in_count AS pitcher_total_in_count,
            pm.pct_shrunk AS pitcher_pct_shrunk,
            br.batter_swings,
            br.batter_whiffs,
            lg.league_whiff_rate,
            (br.batter_whiffs + {k} * lg.league_whiff_rate)
                / (br.batter_swings + {k})
                AS batter_whiff_shrunk,
            ((br.batter_whiffs + {k} * lg.league_whiff_rate)
                / (br.batter_swings + {k}))
                - lg.league_whiff_rate
                AS edge_lift,
            pm.pct_shrunk * (
                ((br.batter_whiffs + {k} * lg.league_whiff_rate)
                    / (br.batter_swings + {k}))
                - lg.league_whiff_rate
            ) AS edge_weighted
        FROM pairs
        JOIN pitcher_pitch_mix pm
            ON pairs.pitcher = pm.pitcher AND pairs.season = pm.season
        JOIN batter_rollup br
            ON pairs.batter = br.batter AND pairs.season = br.season
           AND pm.pitch_type = br.pitch_type
           AND pm.balls = br.balls AND pm.strikes = br.strikes
        JOIN league lg
            ON pm.season = lg.season
           AND pm.pitch_type = lg.pitch_type
           AND pm.balls = lg.balls AND pm.strikes = lg.strikes
        ORDER BY season, pitcher, batter, pitch_type, balls, strikes
    """
    write_derived_parquet(con, sql, "matchup_edges")


# --- Summary view ---------------------------------------------------------

MATCHUP_EDGES_TOP_SQL = """
CREATE OR REPLACE VIEW matchup_edges_top AS
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY pitcher, batter, season
               ORDER BY edge_weighted DESC NULLS LAST
           ) AS edge_rank
    FROM matchup_edges
    WHERE edge_weighted IS NOT NULL
)
SELECT
    pitcher,
    ANY_VALUE(player_name) AS player_name,
    batter,
    season,
    MAX(CASE WHEN edge_rank = 1 THEN pitch_type END)        AS best_pitch_type,
    MAX(CASE WHEN edge_rank = 1 THEN balls END)             AS best_balls,
    MAX(CASE WHEN edge_rank = 1 THEN strikes END)           AS best_strikes,
    MAX(CASE WHEN edge_rank = 1 THEN edge_weighted END)     AS best_edge_weighted,
    MAX(CASE WHEN edge_rank = 1 THEN edge_lift END)         AS best_edge_lift,
    MAX(CASE WHEN edge_rank = 1 THEN pitcher_n END)         AS best_edge_pitcher_n,
    MAX(CASE WHEN edge_rank = 1 THEN batter_swings END)     AS best_edge_batter_swings,
    MAX(CASE WHEN edge_rank = 2 THEN pitch_type END)        AS second_pitch_type,
    MAX(CASE WHEN edge_rank = 2 THEN edge_weighted END)     AS second_edge_weighted,
    MAX(CASE WHEN edge_rank = 3 THEN pitch_type END)        AS third_pitch_type,
    MAX(CASE WHEN edge_rank = 3 THEN edge_weighted END)     AS third_edge_weighted,
    COUNT(*)                                                AS n_edge_cells,
    SUM(pitcher_n)                                          AS pitcher_pitches_in_matched_cells
FROM ranked
GROUP BY pitcher, batter, season
"""
