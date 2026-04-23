"""Pitcher-centric derived tables."""

from __future__ import annotations

import duckdb
from loguru import logger

from baseball.config import SHRINKAGE_K
from baseball.derived._common import write_derived_parquet

# Statcast description values that indicate a swing.
SWING_DESCRIPTIONS = (
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "hit_into_play",
)
# Swing descriptions that are specifically whiffs (bat misses the ball entirely).
WHIFF_DESCRIPTIONS = ("swinging_strike", "swinging_strike_blocked")
# Statcast `events` values that count as strikeouts for put-away rate.
STRIKEOUT_EVENTS = ("strikeout", "strikeout_double_play")


def _sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


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


def build_pitcher_zone_tendency(con: duckdb.DuckDBPyConnection) -> None:
    """pitcher_zone_tendency — zone frequency by (pitcher, season, pitch_type, balls, strikes, zone).

    Statcast zones 1-9 are inside the strike zone (3x3 grid) and 11-14 are
    out-of-zone quadrants. Rows with NULL or out-of-range zones are dropped.

    Rate columns mirror pitcher_pitch_mix:
      pct_raw     = zone_count / total_in_bucket
      pct_shrunk  = (zone_count + k * league_pct) / (total_in_bucket + k)
    where `total_in_bucket` is this pitcher's pitches of this type in this count.
    """
    k = SHRINKAGE_K["zone_tendency"]
    logger.info(f"Building pitcher_zone_tendency (shrinkage k={k})")

    sql = f"""
        WITH regular AS (
            SELECT
                pitcher, player_name, season,
                CAST(balls AS SMALLINT) AS balls,
                CAST(strikes AS SMALLINT) AS strikes,
                pitch_type,
                CAST(zone AS SMALLINT) AS zone
            FROM pitches
            WHERE game_type = 'R'
              AND pitch_type IS NOT NULL
              AND pitcher IS NOT NULL
              AND zone IS NOT NULL
              AND zone BETWEEN 1 AND 14
              AND balls BETWEEN 0 AND 3
              AND strikes BETWEEN 0 AND 2
        ),
        pitcher_agg AS (
            SELECT pitcher, season, pitch_type, balls, strikes, zone,
                   COUNT(*) AS zone_count
            FROM regular GROUP BY 1, 2, 3, 4, 5, 6
        ),
        pitcher_totals AS (
            SELECT pitcher, season, pitch_type, balls, strikes,
                   SUM(zone_count) AS total_in_bucket
            FROM pitcher_agg GROUP BY 1, 2, 3, 4, 5
        ),
        league_agg AS (
            SELECT season, pitch_type, balls, strikes, zone,
                   COUNT(*) AS league_zone_count
            FROM regular GROUP BY 1, 2, 3, 4, 5
        ),
        league_totals AS (
            SELECT season, pitch_type, balls, strikes,
                   SUM(league_zone_count) AS league_total
            FROM league_agg GROUP BY 1, 2, 3, 4
        ),
        names AS (
            SELECT pitcher, season, ANY_VALUE(player_name) AS player_name
            FROM regular GROUP BY 1, 2
        )
        SELECT
            pa.pitcher,
            n.player_name,
            pa.season,
            pa.pitch_type,
            pa.balls,
            pa.strikes,
            pa.zone,
            pa.zone_count,
            pt.total_in_bucket,
            (la.league_zone_count * 1.0 / lt.league_total) AS league_pct,
            (pa.zone_count * 1.0 / pt.total_in_bucket) AS pct_raw,
            (pa.zone_count
                + {k} * (la.league_zone_count * 1.0 / lt.league_total))
                / (pt.total_in_bucket + {k}) AS pct_shrunk
        FROM pitcher_agg pa
        JOIN pitcher_totals pt USING (pitcher, season, pitch_type, balls, strikes)
        JOIN league_agg la USING (season, pitch_type, balls, strikes, zone)
        JOIN league_totals lt USING (season, pitch_type, balls, strikes)
        JOIN names n USING (pitcher, season)
        ORDER BY season, pitcher, pitch_type, balls, strikes, zone
    """
    write_derived_parquet(con, sql, "pitcher_zone_tendency")


def build_pitcher_sequences_2pitch(con: duckdb.DuckDBPyConnection) -> None:
    """pitcher_sequences_2pitch — every 2-pitch sequence within a plate appearance.

    Key: (pitcher, season, balls_before_p1, strikes_before_p1, pitch1_type, pitch2_type)

    A "sequence" is any two consecutive pitches from the same pitcher in the
    same PA (game_pk, at_bat_number), detected via LAG() over pitch_number.

    Metrics:
      whiff_rate    = whiffs_on_p2 / swings_on_p2
      put_away_rate = put_aways / two_strike_p2
                      (subset of sequences where p2 was thrown with 2 strikes
                       on the batter — i.e., where a K was possible on p2)

    Both metrics ship with league comparison and empirical-Bayes shrunk
    estimates. NULL rates mean "undefined" (no swings, or no 2-strike chances).
    When the pitcher has 0 swings but the league has data, `whiff_rate_shrunk`
    still resolves to the league rate — the prior becomes the best guess.
    """
    k_whiff = SHRINKAGE_K["whiff_rate_seq"]
    k_pa = SHRINKAGE_K["put_away_rate_seq"]
    logger.info(
        f"Building pitcher_sequences_2pitch (k_whiff={k_whiff}, k_put_away={k_pa})"
    )

    swings = _sql_in(SWING_DESCRIPTIONS)
    whiffs = _sql_in(WHIFF_DESCRIPTIONS)
    ks = _sql_in(STRIKEOUT_EVENTS)

    sql = f"""
        WITH regular AS (
            SELECT
                pitcher, player_name, season, game_pk, at_bat_number, pitch_number,
                pitch_type,
                CAST(balls AS SMALLINT) AS balls,
                CAST(strikes AS SMALLINT) AS strikes,
                description, events
            FROM pitches
            WHERE game_type = 'R'
              AND pitch_type IS NOT NULL
              AND pitcher IS NOT NULL
              AND pitch_number IS NOT NULL
              AND balls BETWEEN 0 AND 3
              AND strikes BETWEEN 0 AND 2
        ),
        enriched AS (
            SELECT
                pitcher, player_name, season,
                pitch_type AS pitch2_type,
                balls AS balls_before_p2,
                strikes AS strikes_before_p2,
                description, events,
                LAG(pitch_type) OVER w AS pitch1_type,
                LAG(balls) OVER w AS balls_before_p1,
                LAG(strikes) OVER w AS strikes_before_p1
            FROM regular
            WINDOW w AS (
                PARTITION BY game_pk, at_bat_number ORDER BY pitch_number
            )
        ),
        pairs AS (
            SELECT * FROM enriched WHERE pitch1_type IS NOT NULL
        ),
        pitcher_seq AS (
            SELECT
                pitcher, season,
                CAST(balls_before_p1 AS SMALLINT) AS balls_before_p1,
                CAST(strikes_before_p1 AS SMALLINT) AS strikes_before_p1,
                pitch1_type, pitch2_type,
                COUNT(*) AS n_sequences,
                SUM(CASE WHEN description IN ({swings}) THEN 1 ELSE 0 END) AS swings_on_p2,
                SUM(CASE WHEN description IN ({whiffs}) THEN 1 ELSE 0 END) AS whiffs_on_p2,
                SUM(CASE WHEN strikes_before_p2 = 2 THEN 1 ELSE 0 END) AS two_strike_p2,
                SUM(CASE WHEN strikes_before_p2 = 2 AND events IN ({ks}) THEN 1 ELSE 0 END)
                    AS put_aways
            FROM pairs GROUP BY 1, 2, 3, 4, 5, 6
        ),
        league_seq AS (
            SELECT
                season,
                CAST(balls_before_p1 AS SMALLINT) AS balls_before_p1,
                CAST(strikes_before_p1 AS SMALLINT) AS strikes_before_p1,
                pitch1_type, pitch2_type,
                SUM(CASE WHEN description IN ({swings}) THEN 1 ELSE 0 END) AS league_swings,
                SUM(CASE WHEN description IN ({whiffs}) THEN 1 ELSE 0 END) AS league_whiffs,
                SUM(CASE WHEN strikes_before_p2 = 2 THEN 1 ELSE 0 END) AS league_two_strike,
                SUM(CASE WHEN strikes_before_p2 = 2 AND events IN ({ks}) THEN 1 ELSE 0 END)
                    AS league_put_aways
            FROM pairs GROUP BY 1, 2, 3, 4, 5
        ),
        names AS (
            SELECT pitcher, season, ANY_VALUE(player_name) AS player_name
            FROM pairs GROUP BY 1, 2
        )
        SELECT
            ps.pitcher,
            n.player_name,
            ps.season,
            ps.balls_before_p1,
            ps.strikes_before_p1,
            ps.pitch1_type,
            ps.pitch2_type,
            ps.n_sequences,
            ps.swings_on_p2,
            ps.whiffs_on_p2,
            ps.two_strike_p2,
            ps.put_aways,
            CASE WHEN ps.swings_on_p2 > 0
                 THEN ps.whiffs_on_p2 * 1.0 / ps.swings_on_p2 END AS whiff_rate_raw,
            CASE WHEN ps.two_strike_p2 > 0
                 THEN ps.put_aways * 1.0 / ps.two_strike_p2 END AS put_away_rate_raw,
            CASE WHEN ls.league_swings > 0
                 THEN ls.league_whiffs * 1.0 / ls.league_swings END AS league_whiff_rate,
            CASE WHEN ls.league_two_strike > 0
                 THEN ls.league_put_aways * 1.0 / ls.league_two_strike
                 END AS league_put_away_rate,
            CASE WHEN ls.league_swings > 0
                 THEN (ps.whiffs_on_p2
                        + {k_whiff} * (ls.league_whiffs * 1.0 / ls.league_swings))
                       / (ps.swings_on_p2 + {k_whiff})
                 END AS whiff_rate_shrunk,
            CASE WHEN ls.league_two_strike > 0
                 THEN (ps.put_aways
                        + {k_pa} * (ls.league_put_aways * 1.0 / ls.league_two_strike))
                       / (ps.two_strike_p2 + {k_pa})
                 END AS put_away_rate_shrunk
        FROM pitcher_seq ps
        JOIN league_seq ls USING (
            season, balls_before_p1, strikes_before_p1, pitch1_type, pitch2_type
        )
        JOIN names n USING (pitcher, season)
        ORDER BY season, pitcher, balls_before_p1, strikes_before_p1,
                 pitch1_type, pitch2_type
    """
    write_derived_parquet(con, sql, "pitcher_sequences_2pitch")
