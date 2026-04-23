# The Database, in Plain English

A guide to every table in the pitch-analytics database. This is written for anyone who knows baseball but doesn't want to read SQL — an analyst, a product person, a baseball fan who wants to explore, or future-you returning after six months.

There are **8 tables total**:
- **1 raw:** `pitches` (every pitch ever thrown since 2015)
- **6 derived:** pre-computed summaries that answer common questions about pitchers and batters
- **1 derived + 1 convenience view:** `matchup_edges` (pitcher vs batter) and `matchup_edges_top` (its one-row-per-pairing summary)

---

## Quick primer on baseball terms the tables use

- **Pitch type codes.** Every pitch is tagged with a 2-letter code. The common ones:
  - `FF` = 4-seam fastball · `SI` = sinker · `FC` = cutter
  - `SL` = slider · `ST` = sweeper · `CU` = curveball · `KC` = knuckle-curve
  - `CH` = changeup · `FS` = splitter · `FO` = forkball
- **Count.** The balls-strikes count before the pitch. `0-0` = first pitch of the at-bat. `3-2` = full count.
- **Zone.** Statcast splits the area around home plate into 14 regions. Zones 1–9 are inside the strike zone (a 3×3 grid, zone 5 is dead center). Zones 11–14 are the four out-of-zone quadrants.
- **Whiff.** A swing that misses entirely (strike). Not the same as a foul ball, which is also a swing but counts as contact.
- **Chase.** Swinging at a pitch *outside* the strike zone. Low chase rate = disciplined hitter.
- **Put-away rate.** On 2-strike counts, how often the pitcher gets the strikeout. Key measure of a pitcher's "finish."
- **Raw vs. shrunk rates.** If a rookie goes 2-for-3 in their first game, their batting average is .667 "raw" — but nobody thinks they'll really hit .667 over a full season. A **shrunk** rate does the statistical sensible thing: pulls small samples toward the league average until enough evidence accumulates. Every rate column in every table has both a `_raw` and `_shrunk` version. Use `_shrunk` for anything with modest sample size; see [SAMPLE_SIZES.md](SAMPLE_SIZES.md) for the details.

---

## 1. `pitches` — every pitch thrown since 2015

This is the foundation. Every other table is built from this one.

**What's in it:** One row per pitch, from 2015 Opening Day through the latest nightly update. Each row has ~118 columns: the pitcher's name, the batter's MLBAM ID, the date, the pitch type and velocity, where it crossed the plate, the outcome (ball / called strike / swing / contact), and dozens more Statcast tracking fields.

**Scope:** Includes **all** game types — regular season (`R`), spring training (`S`), and every round of postseason (`F`/`D`/`L`/`W`). The `game_type` column tells you which. Most derived tables below filter to regular season only; if you want to analyze specifically spring training or postseason, query `pitches` directly with `WHERE game_type = 'S'` or similar.

**Partitioned by season + month.** DuckDB auto-adds `season` and `month` columns based on the directory structure, so `WHERE season = 2024` is very fast.

**Things you'd use it for:**
- "Show me every pitch Skubal threw in his September 15 start."
- "How many pitches did batter Juan Soto see in 2024?"
- "What's the average exit velocity on hit-into-play events off 4-seamers?"

---

## 2. `pitcher_pitch_mix` — what each pitcher throws in each count

**The question it answers:** When pitcher X is in a 0-2 count, what fraction of his pitches are fastballs vs. sliders vs. changeups? How does that differ from what the average MLB pitcher does?

**Why it matters:** This is the pitcher's **tendency map**. Some pitchers pound 4-seamers in 0-2; others pivot to a putaway breaking ball. Knowing a pitcher's pattern is half the battle for hitters — and identifying patterns is the table's job.

**Scope:** Regular season only. One row per `(pitcher, season, balls, strikes, pitch_type)`.

**Columns explained:**

| Column | Meaning |
|---|---|
| `pitcher` | The pitcher's MLBAM ID |
| `player_name` | The pitcher's name, e.g. `"Skubal, Tarik"` |
| `season` | Year |
| `balls`, `strikes` | The count before the pitch (0-0, 1-2, etc.) |
| `pitch_type` | 2-letter code (FF, SL, CH, etc.) |
| `pitch_count` | **Sample size** — how many of this pitch type the pitcher threw in this count this season |
| `total_in_count` | How many pitches total the pitcher threw in this count (the denominator for `pct_raw`) |
| `league_pct` | The MLB-average share of this pitch type in this count (for comparison) |
| `pct_raw` | `pitch_count / total_in_count` — the pitcher's empirical usage rate |
| `pct_shrunk` | The rate adjusted toward league when sample size is small. Use this for display. |

**Example finding (2024):** In 0-2 counts, Tarik Skubal throws his changeup **31% of the time** — nearly 3× the league rate of 11%. That's why his changeup gets so many strikeouts: hitters expect a fastball and get something 10 mph slower.

**Example question you could answer:** "Which pitchers increase their breaking-ball usage the most when ahead in the count?"

---

## 3. `pitcher_zone_tendency` — where each pitcher locates each pitch type

**The question:** When Snell throws a curveball in a 1-2 count, which part of the plate does it usually go to?

**Why it matters:** Same pitch, different pitchers, very different locations. Some sliders live glove-side and out of the zone (designed to get chases). Others catch the top of the zone (meant to be called strikes). Mapping these tendencies lets you anticipate where the ball is going before it's thrown.

**Scope:** Regular season only. One row per `(pitcher, season, pitch_type, balls, strikes, zone)`.

**Columns explained:**

| Column | Meaning |
|---|---|
| `pitcher`, `player_name`, `season` | Same as pitch_mix |
| `pitch_type` | Which pitch |
| `balls`, `strikes` | The count |
| `zone` | Which zone (1–9 in-zone, 11–14 out-of-zone) |
| `zone_count` | **Sample size** — how many of this pitch in this zone in this count |
| `total_in_bucket` | Denominator: total pitches of this type in this count |
| `league_pct` | What's the league-average rate for this zone/pitch/count? |
| `pct_raw`, `pct_shrunk` | The pitcher's rate (empirical and shrunk) |

**Example finding:** 49.5% of MLB pitches in 2024 were thrown in the strike zone (zones 1–9), exactly matching the decades-long historical norm. Confirms the data ingest is intact.

**Example question:** "Who throws the most called strikes at the top of the zone with their fastball in 2-strike counts?" → filter by `pitch_type='FF', strikes=2, zone IN (1,2,3)`.

---

## 4. `pitcher_sequences_2pitch` — every 2-pitch combo a pitcher throws

**The question:** When Skubal throws a fastball and immediately follows it with a changeup, what happens to the hitter?

**Why it matters:** This is the **sequencing core of the project**. Pitchers don't pick pitches in isolation — they set up one pitch with another. A well-located fastball at the top of the zone makes the same changeup harder to hit five seconds later. Measuring sequence effectiveness (not just pitch-by-pitch) is what sets this analytics platform apart from Baseball Savant.

**Scope:** Regular season only. One row per `(pitcher, season, balls_before_p1, strikes_before_p1, pitch1_type, pitch2_type)`. A "sequence" is any two consecutive pitches from the same pitcher to the same batter within one plate appearance.

**Columns explained:**

| Column | Meaning |
|---|---|
| `pitch1_type`, `pitch2_type` | The two-pitch combo, e.g. FF then CH |
| `balls_before_p1`, `strikes_before_p1` | The count when pitch 1 was thrown |
| `n_sequences` | **Sample size** — how many times this combo happened |
| `swings_on_p2` | How many times the batter swung at pitch 2 |
| `whiffs_on_p2` | How many of those swings missed |
| `two_strike_p2` | Subset of sequences where pitch 2 came with 2 strikes (i.e., could have ended the at-bat) |
| `put_aways` | How many of those 2-strike sequences actually ended in a strikeout |
| `whiff_rate_raw/shrunk` | Miss rate on pitch 2: `whiffs / swings` |
| `league_whiff_rate` | What the average pitcher gets on this same combo |
| `put_away_rate_raw/shrunk` | How often a 2-strike pitch 2 ends the PA with a K |
| `league_put_away_rate` | League baseline |

**Example finding:** David Robertson's FC→FC (back-to-back cutters) gets a strikeout **45.9% of the time** on 2-strike pitch 2 — league-leading. Skubal's signature FF→CH gets a K 33.3% of the time in 0-2 counts, **2.5× league average** (13.1%).

**Example question:** "Which pitchers have the biggest whiff-rate edge on their FF→SL two-pitch sequence compared to league?" → filter `pitch1_type='FF', pitch2_type='SL'`, sort by `whiff_rate_shrunk - league_whiff_rate`.

---

## 5. `batter_whiff_profile` — where each batter whiffs

**The question:** Which pitches, in which zones, does batter X swing through?

**Why it matters:** Every hitter has holes. Some can't lay off the high fastball; some can't touch a slider on the outer third. Mapping a batter's holes is what pitchers mean by "scouting" — it's how they plan an at-bat before they ever see the hitter.

**Scope:** Regular season, only pitches the batter swung at. One row per `(batter, season, pitch_type, zone, balls, strikes)`. Note: the table has no `batter_name` column because Statcast's raw data only names the pitcher (phase 2 will add a name lookup).

**Columns explained:**

| Column | Meaning |
|---|---|
| `batter` | The batter's MLBAM ID |
| `pitch_type`, `zone`, `balls`, `strikes` | The situation |
| `swings` | **Sample size** — how many times this batter swung at this pitch/zone/count |
| `whiffs` | How many of those missed entirely |
| `whiff_rate_raw/shrunk` | Miss rate: `whiffs / swings` |
| `league_whiff_rate` | League-average miss rate for the same bucket |

**Example finding:** Luis Arraez (three-time batting champion) misses sliders only **11.9% of the time** — half the league rate. He's the hardest batter in baseball to strike out with a slider.

**Example question:** "Which batters are most vulnerable to a high fastball in 2-strike counts?" → filter `pitch_type='FF', zone IN (1,2,3), strikes=2`, sort by `whiff_rate_shrunk`.

---

## 6. `batter_swing_decisions` — chase% and zone-swing% by count

**The question:** When batter X sees a pitch in a particular count, is he hacking at anything (chaser) or laying off pitches outside the zone (disciplined)?

**Why it matters:** Plate discipline is a fundamental hitter skill. Chase rate and zone-swing rate are the two numbers that together describe "is this guy selective." They drive how pitchers attack him.

**Scope:** Regular season. One row per `(batter, season, balls, strikes)`.

**Columns explained:**

| Column | Meaning |
|---|---|
| `batter`, `season`, `balls`, `strikes` | The situation |
| `pitches_seen` | Total pitches the batter saw in this count |
| `pitches_in_zone` | How many of those were actual strikes (zones 1–9) |
| `pitches_out_of_zone` | How many were balls (zones 11–14) |
| `swings_total` | How many swings, total |
| `swings_in_zone` | How many swings at in-zone pitches |
| `swings_out_of_zone` | How many swings at balls |
| `z_swing_rate_raw/shrunk` | `swings_in_zone / pitches_in_zone`. High = aggressive hitter |
| `chase_rate_raw/shrunk` | `swings_out_of_zone / pitches_out_of_zone`. **This is the discipline metric.** Low = selective |
| `league_z_swing_rate`, `league_chase_rate` | Averages for comparison |

**Example finding (2024):** Juan Soto chases **18.0%** of out-of-zone pitches — best in MLB. Salvador Perez, a famously aggressive hitter, chases **42.9%** — more than 2× Soto's rate.

**Example question:** "Which batters swing at more in-zone pitches as strikes accumulate (i.e., get more defensive)?" → `SELECT batter, strikes, z_swing_rate_shrunk GROUP BY batter, strikes`.

---

## 7. `batter_vs_sequences` — how each batter reacts to 2-pitch combos

**The question:** When any pitcher throws pitch A to batter Y and then follows with pitch B, how does batter Y respond to that specific sequence?

**Why it matters:** Mirror image of `pitcher_sequences_2pitch`. A hitter may be vulnerable to a specific pitch-pair he's seen across many pitchers. Surfacing that vulnerability is how teams build matchup-specific game plans.

**Scope:** Regular season. One row per `(batter, season, pitch1_type, pitch2_type)`. Unlike pitcher_sequences_2pitch, this rolls up across all counts — because a batter's *general* reaction to FF→SL is more stable than any one count's numbers.

**Columns explained:**

| Column | Meaning |
|---|---|
| `batter`, `pitch1_type`, `pitch2_type`, `season` | The combo the batter faced |
| `n_sequences` | **Sample size** — how many times this batter saw this combo |
| `swings_on_p2`, `whiffs_on_p2` | Swing / miss counts on pitch 2 |
| `two_strike_p2` | Subset where pitch 2 came with 2 strikes (strikeout chances) |
| `strikeouts_on_p2` | How many of those became Ks |
| `whiff_rate_raw/shrunk` | Miss rate on pitch 2 |
| `strikeout_rate_raw/shrunk` | K rate when pitch 2 comes with 2 strikes |
| `league_whiff_rate`, `league_strikeout_rate` | Baselines |

**Example question:** "Which batters are most likely to strike out on a FF→SL sequence compared to league?" → filter `pitch1_type='FF', pitch2_type='SL'`, sort by `strikeout_rate_shrunk`.

---

## 8. `matchup_edges` — pitcher tendencies × batter weaknesses

**The question this exists for:** If pitcher X throws pitch Y in count Z to batter W, how much of an edge does the pitcher have? Where's the single biggest leverage spot in this specific pitcher-batter matchup?

**Why it matters:** This is the **payoff table**. Pitcher A throws lots of changeups in 0-2. Batter B whiffs on changeups in 0-2 30% more than league average. Matchup edges surfaces that combo as a high-leverage opportunity — somewhere the pitcher should lean in. Every other derived table feeds into this one.

**Scope:** Regular season. One row per `(pitcher, batter, season, pitch_type, balls, strikes)` **for every pitcher-batter pair that actually met** (at least one pitch in the season) AND where both have data for that specific pitch+count bucket.

**Row count is big** (~3.85M for 2024) because it's a cross-join. That's intentional — see `matchup_edges_top` below for the one-row-per-pairing summary.

**Columns explained:**

| Column | Meaning |
|---|---|
| `pitcher`, `player_name`, `batter`, `season` | The pairing |
| `pitch_type`, `balls`, `strikes` | The situation being evaluated |
| `pitcher_n` | **Pitcher sample** — how many times the pitcher has thrown this pitch in this count |
| `pitcher_total_in_count` | Pitcher's total pitches in this count |
| `pitcher_pct_shrunk` | How often the pitcher throws this pitch in this count (his propensity) |
| `batter_swings`, `batter_whiffs` | **Batter sample** — swings and whiffs this batter has had against this pitch+count (rolled up across zones) |
| `batter_whiff_shrunk` | The batter's shrunk whiff rate on this pitch+count |
| `league_whiff_rate` | League-average miss rate at the same pitch+count |
| `edge_lift` | `batter_whiff_shrunk - league_whiff_rate` — how much **more** this batter whiffs than average. Pure batter property. |
| `edge_weighted` | `pitcher_pct_shrunk × edge_lift` — **leverage**, the key metric. Combines "the pitcher actually throws this" with "the batter can't hit this." |

**How to read the edge metrics:**
- `edge_lift = 0.15` means this batter whiffs at this pitch+count 15 percentage points more than league. Big vulnerability.
- `edge_weighted` adjusts for how often the pitcher throws the pitch. A huge vulnerability on a pitch the pitcher never uses doesn't matter — `pitcher_pct_shrunk = 0.02` would crush the weighted score.
- **Sort by `edge_weighted DESC`** to find the real leverage spots.

**Sample size thresholds:** From SAMPLE_SIZES.md: filter to `pitcher_n ≥ 50 AND batter_swings ≥ 30` before surfacing edges to users. Smaller samples are noise.

**Example finding:** When Skubal faces Juan Soto, his biggest leverage point is **CH in 1-2 counts**: Soto whiffs on changeups in 1-2 about 6.4 pp more than league average, and Skubal throws CH 31% of the time in that count. That's the single pitch a rational Skubal would pick against Soto in 1-2.

**Example question:** "What are the 10 biggest matchup edges in all of MLB in 2024?" → `SELECT * FROM matchup_edges WHERE pitcher_n >= 50 AND batter_swings >= 30 ORDER BY edge_weighted DESC LIMIT 10`.

---

## 9. `matchup_edges_top` — one row per pairing, top edges surfaced

A convenience view (not a separate Parquet file) built on top of `matchup_edges`. It rolls up the long table to one row per `(pitcher, batter, season)` with the **top 3 edges surfaced as columns**. Exactly what a frontend pairing-page wants.

**Scope:** Regular season. One row per unique pitcher-batter pair that met at least once.

**Columns explained:**

| Column | Meaning |
|---|---|
| `pitcher`, `player_name`, `batter`, `season` | The pairing |
| `best_pitch_type`, `best_balls`, `best_strikes` | The single biggest edge for the pitcher: which pitch, which count |
| `best_edge_weighted` | The leverage score of that top edge |
| `best_edge_lift` | The whiff-rate lift of the top edge (how much more the batter whiffs than league) |
| `best_edge_pitcher_n`, `best_edge_batter_swings` | Sample sizes backing the top edge |
| `second_pitch_type`, `second_edge_weighted` | The 2nd-biggest edge |
| `third_pitch_type`, `third_edge_weighted` | The 3rd-biggest edge |
| `n_edge_cells` | How many distinct (pitch, count) cells have any edge data for this matchup |
| `pitcher_pitches_in_matched_cells` | Total pitches the pitcher has thrown across all the matched cells |

**Example use:** Build a pitcher-vs-batter scouting card:

```sql
SELECT player_name AS pitcher, batter,
       best_pitch_type, best_balls || '-' || best_strikes AS best_count,
       ROUND(best_edge_weighted * 1000, 1) AS leverage_x1000,
       second_pitch_type, third_pitch_type
FROM matchup_edges_top
WHERE player_name = 'Skubal, Tarik'
ORDER BY best_edge_weighted DESC
LIMIT 10;
```

That gives you Skubal's 10 highest-leverage matchups in the league, with the top three go-to pitches for each.

---

## A few final notes

- **Every rate column ships in both `_raw` and `_shrunk` forms.** For any UI that surfaces a rate to users, prefer `_shrunk` unless you know the sample is large.
- **Every derived table has a sample-size column** (`pitch_count`, `zone_count`, `swings`, `n_sequences`, etc.). Apply minimum-sample thresholds from [SAMPLE_SIZES.md](SAMPLE_SIZES.md) before showing stats.
- **Only regular-season data lives in the derived tables.** Spring training (`game_type='S'`) and postseason (`F`/`D`/`L`/`W`) live only in the raw `pitches` table. If you need them, query `pitches` directly.
- **The raw `pitches` table is the source of truth.** If a derived table gives a surprising answer, cross-check by querying `pitches` directly — the raw data has `~118 columns` per pitch, and nothing was dropped during ingest.
