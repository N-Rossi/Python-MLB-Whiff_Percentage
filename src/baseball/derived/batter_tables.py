"""Batter-centric derived tables.

Note: Statcast's raw CSV does not include a batter name column — `player_name`
in the pitch data is the *pitcher's* name. Batter tables therefore carry only
the MLBAM `batter` ID. A name-lookup helper can be added in a later phase
(pybaseball exposes the Chadwick register).
"""

from __future__ import annotations

import duckdb
from loguru import logger

from baseball.config import SHRINKAGE_K
from baseball.derived._common import write_derived_parquet
from baseball.derived.pitcher_tables import (
    STRIKEOUT_EVENTS,
    SWING_DESCRIPTIONS,
    WHIFF_DESCRIPTIONS,
    _sql_in,
)


def build_batter_whiff_profile(con: duckdb.DuckDBPyConnection) -> None:
    """batter_whiff_profile — whiff rate by (batter, season, pitch_type, zone, count).

    Scope: regular season, rows where the batter swung (so whiff_rate denominator
    > 0 by construction). Zones 1-9 are in-zone; 11-14 out.

    Columns:
      swings            — batter's swings at this pitch_type / zone / count
      whiffs            — of those, how many missed (swinging_strike*)
      whiff_rate_raw    — whiffs / swings
      league_whiff_rate — league rate at the same (pitch_type, zone, count) bucket
      whiff_rate_shrunk — empirical-Bayes blend of raw toward league (k=50)
    """
    k = SHRINKAGE_K["whiff_profile"]
    swings = _sql_in(SWING_DESCRIPTIONS)
    whiffs = _sql_in(WHIFF_DESCRIPTIONS)
    logger.info(f"Building batter_whiff_profile (shrinkage k={k})")

    sql = f"""
        WITH swings_only AS (
            SELECT
                batter,
                season,
                pitch_type,
                CAST(zone AS SMALLINT) AS zone,
                CAST(balls AS SMALLINT) AS balls,
                CAST(strikes AS SMALLINT) AS strikes,
                description
            FROM pitches
            WHERE game_type = 'R'
              AND pitch_type IS NOT NULL
              AND batter IS NOT NULL
              AND zone IS NOT NULL AND zone BETWEEN 1 AND 14
              AND balls BETWEEN 0 AND 3
              AND strikes BETWEEN 0 AND 2
              AND description IN ({swings})
        ),
        batter_agg AS (
            SELECT
                batter, season, pitch_type, zone, balls, strikes,
                COUNT(*) AS swings,
                SUM(CASE WHEN description IN ({whiffs}) THEN 1 ELSE 0 END) AS whiffs
            FROM swings_only
            GROUP BY 1, 2, 3, 4, 5, 6
        ),
        league_agg AS (
            SELECT
                season, pitch_type, zone, balls, strikes,
                COUNT(*) AS league_swings,
                SUM(CASE WHEN description IN ({whiffs}) THEN 1 ELSE 0 END) AS league_whiffs
            FROM swings_only
            GROUP BY 1, 2, 3, 4, 5
        )
        SELECT
            ba.batter,
            ba.season,
            ba.pitch_type,
            ba.zone,
            ba.balls,
            ba.strikes,
            ba.swings,
            ba.whiffs,
            (ba.whiffs * 1.0 / ba.swings) AS whiff_rate_raw,
            (la.league_whiffs * 1.0 / la.league_swings) AS league_whiff_rate,
            (ba.whiffs + {k} * (la.league_whiffs * 1.0 / la.league_swings))
                / (ba.swings + {k}) AS whiff_rate_shrunk
        FROM batter_agg ba
        JOIN league_agg la USING (season, pitch_type, zone, balls, strikes)
        ORDER BY season, batter, pitch_type, zone, balls, strikes
    """
    write_derived_parquet(con, sql, "batter_whiff_profile")


def build_batter_swing_decisions(con: duckdb.DuckDBPyConnection) -> None:
    """batter_swing_decisions — chase% / z-swing% by (batter, season, balls, strikes).

    Denominators are pitches *in* the relevant zone (not swings at).

      z_swing_rate_raw = swings_in_zone / pitches_in_zone
      chase_rate_raw   = swings_out_of_zone / pitches_out_of_zone

    Both columns come with league comparison and shrunk variants (k=50).
    """
    k_z = SHRINKAGE_K["z_swing_rate"]
    k_c = SHRINKAGE_K["chase_rate"]
    swings = _sql_in(SWING_DESCRIPTIONS)
    logger.info(
        f"Building batter_swing_decisions (k_z_swing={k_z}, k_chase={k_c})"
    )

    sql = f"""
        WITH filtered AS (
            SELECT
                batter, season,
                CAST(balls AS SMALLINT) AS balls,
                CAST(strikes AS SMALLINT) AS strikes,
                CAST(zone AS SMALLINT) AS zone,
                (description IN ({swings}))::INTEGER AS is_swing
            FROM pitches
            WHERE game_type = 'R'
              AND batter IS NOT NULL
              AND zone IS NOT NULL AND zone BETWEEN 1 AND 14
              AND balls BETWEEN 0 AND 3
              AND strikes BETWEEN 0 AND 2
        ),
        batter_agg AS (
            SELECT
                batter, season, balls, strikes,
                COUNT(*) AS pitches_seen,
                SUM(CASE WHEN zone BETWEEN 1 AND 9 THEN 1 ELSE 0 END) AS pitches_in_zone,
                SUM(CASE WHEN zone BETWEEN 11 AND 14 THEN 1 ELSE 0 END) AS pitches_out_of_zone,
                SUM(is_swing) AS swings_total,
                SUM(CASE WHEN zone BETWEEN 1 AND 9 THEN is_swing ELSE 0 END) AS swings_in_zone,
                SUM(CASE WHEN zone BETWEEN 11 AND 14 THEN is_swing ELSE 0 END) AS swings_out_of_zone
            FROM filtered
            GROUP BY 1, 2, 3, 4
        ),
        league_agg AS (
            SELECT
                season, balls, strikes,
                SUM(CASE WHEN zone BETWEEN 1 AND 9 THEN 1 ELSE 0 END) AS league_in_zone,
                SUM(CASE WHEN zone BETWEEN 11 AND 14 THEN 1 ELSE 0 END) AS league_out_of_zone,
                SUM(CASE WHEN zone BETWEEN 1 AND 9 THEN is_swing ELSE 0 END) AS league_z_swings,
                SUM(CASE WHEN zone BETWEEN 11 AND 14 THEN is_swing ELSE 0 END) AS league_chases
            FROM filtered
            GROUP BY 1, 2, 3
        )
        SELECT
            ba.batter,
            ba.season,
            ba.balls,
            ba.strikes,
            ba.pitches_seen,
            ba.pitches_in_zone,
            ba.pitches_out_of_zone,
            ba.swings_total,
            ba.swings_in_zone,
            ba.swings_out_of_zone,
            CASE WHEN la.league_in_zone > 0
                 THEN la.league_z_swings * 1.0 / la.league_in_zone END
                AS league_z_swing_rate,
            CASE WHEN la.league_out_of_zone > 0
                 THEN la.league_chases * 1.0 / la.league_out_of_zone END
                AS league_chase_rate,
            CASE WHEN ba.pitches_in_zone > 0
                 THEN ba.swings_in_zone * 1.0 / ba.pitches_in_zone END
                AS z_swing_rate_raw,
            CASE WHEN ba.pitches_out_of_zone > 0
                 THEN ba.swings_out_of_zone * 1.0 / ba.pitches_out_of_zone END
                AS chase_rate_raw,
            CASE WHEN la.league_in_zone > 0
                 THEN (ba.swings_in_zone
                        + {k_z} * (la.league_z_swings * 1.0 / la.league_in_zone))
                       / (ba.pitches_in_zone + {k_z}) END
                AS z_swing_rate_shrunk,
            CASE WHEN la.league_out_of_zone > 0
                 THEN (ba.swings_out_of_zone
                        + {k_c} * (la.league_chases * 1.0 / la.league_out_of_zone))
                       / (ba.pitches_out_of_zone + {k_c}) END
                AS chase_rate_shrunk
        FROM batter_agg ba
        JOIN league_agg la USING (season, balls, strikes)
        ORDER BY season, batter, balls, strikes
    """
    write_derived_parquet(con, sql, "batter_swing_decisions")


def build_batter_vs_sequences(con: duckdb.DuckDBPyConnection) -> None:
    """batter_vs_sequences — batter outcomes on 2-pitch sequences, aggregated across counts.

    Key: (batter, season, pitch1_type, pitch2_type).

    Same underlying sequence detection as pitcher_sequences_2pitch (LAG over
    pitch_number within (game_pk, at_bat_number)) but grouped by batter and
    flattened across counts.

      whiff_rate      — whiffs_on_p2 / swings_on_p2
      strikeout_rate  — strikeouts_on_p2 / two_strike_p2
                        (subset where p2 was thrown with 2 strikes)
    """
    k_whiff = SHRINKAGE_K["batter_seq_whiff"]
    k_k = SHRINKAGE_K["batter_seq_strikeout"]
    swings = _sql_in(SWING_DESCRIPTIONS)
    whiffs = _sql_in(WHIFF_DESCRIPTIONS)
    ks = _sql_in(STRIKEOUT_EVENTS)
    logger.info(
        f"Building batter_vs_sequences (k_whiff={k_whiff}, k_strikeout={k_k})"
    )

    sql = f"""
        WITH regular AS (
            SELECT
                batter, season, game_pk, at_bat_number, pitch_number,
                pitch_type,
                CAST(strikes AS SMALLINT) AS strikes,
                description, events
            FROM pitches
            WHERE game_type = 'R'
              AND pitch_type IS NOT NULL
              AND batter IS NOT NULL
              AND pitch_number IS NOT NULL
              AND balls BETWEEN 0 AND 3
              AND strikes BETWEEN 0 AND 2
        ),
        enriched AS (
            SELECT
                batter, season,
                pitch_type AS pitch2_type,
                strikes AS strikes_before_p2,
                description, events,
                LAG(pitch_type) OVER w AS pitch1_type
            FROM regular
            WINDOW w AS (
                PARTITION BY game_pk, at_bat_number ORDER BY pitch_number
            )
        ),
        pairs AS (
            SELECT * FROM enriched WHERE pitch1_type IS NOT NULL
        ),
        batter_seq AS (
            SELECT
                batter, season, pitch1_type, pitch2_type,
                COUNT(*) AS n_sequences,
                SUM(CASE WHEN description IN ({swings}) THEN 1 ELSE 0 END) AS swings_on_p2,
                SUM(CASE WHEN description IN ({whiffs}) THEN 1 ELSE 0 END) AS whiffs_on_p2,
                SUM(CASE WHEN strikes_before_p2 = 2 THEN 1 ELSE 0 END) AS two_strike_p2,
                SUM(CASE WHEN strikes_before_p2 = 2 AND events IN ({ks}) THEN 1 ELSE 0 END)
                    AS strikeouts_on_p2
            FROM pairs GROUP BY 1, 2, 3, 4
        ),
        league_seq AS (
            SELECT
                season, pitch1_type, pitch2_type,
                SUM(CASE WHEN description IN ({swings}) THEN 1 ELSE 0 END) AS league_swings,
                SUM(CASE WHEN description IN ({whiffs}) THEN 1 ELSE 0 END) AS league_whiffs,
                SUM(CASE WHEN strikes_before_p2 = 2 THEN 1 ELSE 0 END) AS league_two_strike,
                SUM(CASE WHEN strikes_before_p2 = 2 AND events IN ({ks}) THEN 1 ELSE 0 END)
                    AS league_strikeouts
            FROM pairs GROUP BY 1, 2, 3
        )
        SELECT
            bs.batter,
            bs.season,
            bs.pitch1_type,
            bs.pitch2_type,
            bs.n_sequences,
            bs.swings_on_p2,
            bs.whiffs_on_p2,
            bs.two_strike_p2,
            bs.strikeouts_on_p2,
            CASE WHEN bs.swings_on_p2 > 0
                 THEN bs.whiffs_on_p2 * 1.0 / bs.swings_on_p2 END AS whiff_rate_raw,
            CASE WHEN bs.two_strike_p2 > 0
                 THEN bs.strikeouts_on_p2 * 1.0 / bs.two_strike_p2 END
                AS strikeout_rate_raw,
            CASE WHEN ls.league_swings > 0
                 THEN ls.league_whiffs * 1.0 / ls.league_swings END
                AS league_whiff_rate,
            CASE WHEN ls.league_two_strike > 0
                 THEN ls.league_strikeouts * 1.0 / ls.league_two_strike END
                AS league_strikeout_rate,
            CASE WHEN ls.league_swings > 0
                 THEN (bs.whiffs_on_p2
                        + {k_whiff} * (ls.league_whiffs * 1.0 / ls.league_swings))
                       / (bs.swings_on_p2 + {k_whiff}) END
                AS whiff_rate_shrunk,
            CASE WHEN ls.league_two_strike > 0
                 THEN (bs.strikeouts_on_p2
                        + {k_k} * (ls.league_strikeouts * 1.0 / ls.league_two_strike))
                       / (bs.two_strike_p2 + {k_k}) END
                AS strikeout_rate_shrunk
        FROM batter_seq bs
        JOIN league_seq ls USING (season, pitch1_type, pitch2_type)
        ORDER BY season, batter, pitch1_type, pitch2_type
    """
    write_derived_parquet(con, sql, "batter_vs_sequences")
