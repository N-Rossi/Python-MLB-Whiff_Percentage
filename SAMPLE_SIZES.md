# Sample Size Conventions

Derived tables store **every** sample without filtering — thresholds are applied at query time, not build time. That way we never lose a cell just because it's small, and we can tune thresholds without rebuilding.

Every derived table includes a `sample_size` column (pitch count or PA count backing the row). Consumers are expected to respect the minimums below.

## Default minimum thresholds

Starting points — tune per feature.

### Pitcher tables

| Table | Key | Min sample |
|---|---|---|
| `pitcher_pitch_mix` | (pitcher, season, count, pitch_type) | ≥ 20 pitches in that count |
| `pitcher_zone_tendency` | (pitcher, pitch_type, count) | ≥ 30 pitches |
| `pitcher_sequences_2pitch` | (pitcher, season, pitch1_type, pitch2_type, count_before_pitch1) | ≥ 25 sequences |

### Batter tables

| Table | Key | Min sample |
|---|---|---|
| `batter_whiff_profile` | (batter, pitch_type, zone, count) | ≥ 15 swings |
| `batter_swing_decisions` | (batter, count) | ≥ 100 pitches seen |
| `batter_vs_sequences` | (batter, pitch1_type, pitch2_type) | ≥ 20 sequences |

### Matchup table

| Table | Key | Min sample |
|---|---|---|
| `matchup_edges` | (pitcher, batter, season) | Pitcher ≥ 50 pitches of that type in that count AND batter ≥ 30 pitches seen of that type in that count |

## Shrinkage toward league average

For rate metrics (whiff%, CSW%, chase%, put-away%), derived tables carry two columns:

- `<metric>_raw` — empirical rate (numerator / denominator)
- `<metric>_shrunk` — empirical-Bayes estimate shrunk toward the league rate for the same bucket

Formula:

```
p_shrunk = (n * p_raw + k * p_league) / (n + k)
```

Where:
- `n` = `sample_size` for the cell
- `p_raw` = empirical rate
- `p_league` = league-average rate in the same (pitch_type, count) bucket for that season
- `k` = prior strength — the n at which we trust the empirical rate roughly 50/50 with league

Starting `k` values:

| Metric | k |
|---|---|
| Whiff rate | 50 swings |
| CSW% | 100 pitches |
| Chase% | 50 out-of-zone pitches |
| Put-away rate | 40 two-strike pitches |

Tune by looking at the variance of the empirical distribution — higher between-pitcher variance warrants smaller k (less shrinkage).

## When to filter vs. shrink vs. show raw

- **Hide** cells where even the shrunk estimate is essentially the prior (typically n < 10). Pure noise.
- **Shrink** cells with modest samples (10 ≤ n ≤ ~500). Shrunk is the safe display default.
- **Show raw** cells with plentiful samples (n > ~500). The prior barely moves the needle — shrinking adds no value.
