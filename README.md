# MLB Pitch Analytics Platform

Data infrastructure and analytics for MLB pitch-sequencing and pitcher/batter matchup edges. The repo has three parts:

1. **`src/baseball/`** — the main data pipeline (ingest Statcast → Parquet → DuckDB → derived tables). Phase 1 complete.
2. **`reports/`** — a blog-style archive of standalone one-off analyses. Each report is self-contained and deliberately kept separate from the main pipeline.
3. **`backend/` + `frontend/`** — a legacy FastAPI + React web app that surfaces the first-pitch offspeed report. Will eventually be rewired on top of the new data pipeline; for now it runs against frozen data in `data/legacy/`.

**Documentation:**
- **[TABLES.md](TABLES.md)** — plain-English explanation of every table and column (start here if you're new).
- **[SAMPLE_SIZES.md](SAMPLE_SIZES.md)** — minimum-sample conventions and empirical-Bayes shrinkage approach.
- **[deploy/README.md](deploy/README.md)** — VM deployment: cron / systemd timer setup.

## Status

| Component | State |
|---|---|
| `baseball backfill` (one-time historical ingest) | ✅ works |
| `baseball update` (single-day ingest) | ✅ works |
| `baseball daily-update` (cron entrypoint: ingest + rebuild) | ✅ works |
| `baseball rebuild-derived` | ✅ works — all 7 derived tables |
| `baseball inspect` | ✅ works |
| `baseball query` | ✅ works |
| `baseball shell` (interactive SQL) | ✅ works |
| Nightly cron deployment (systemd / crontab) | ✅ templates ready in `deploy/` |
| Legacy FastAPI + React app | ✅ runs against `data/legacy/` |

## Requirements

- Python **3.11+** (tested on 3.14)
- Node 18+ (only for the legacy frontend)
- ~2 GB free disk for the full 2015–present raw Statcast + derived tables

## Setup

```bash
git clone <repo-url>
cd Python-MLB-Whiff_Percentage

python -m venv .venv

# Activate the venv
source .venv/bin/activate            # macOS / Linux
source .venv/Scripts/activate        # Windows (Git Bash)
.venv\Scripts\activate               # Windows (cmd)
.venv\Scripts\Activate.ps1           # Windows (PowerShell)

pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .                     # registers the `baseball` CLI

cp .env.example .env                 # optional; adjust as needed
baseball --help
```

## Data pipeline

### Ingest

Pulls pitch-level Statcast data from Baseball Savant via `pybaseball`, one week at a time, into partitioned Parquet.

```bash
# Full backfill (2015 through current season). Runs for an hour-ish.
baseball backfill --start-season 2015 --end-season 2026

# Single season
baseball backfill --start-season 2024 --end-season 2024

# Single day (intended for a nightly in-season cron)
baseball update --date 2024-04-15
baseball update                      # defaults to yesterday

# Force re-pull even if the week is already cached
baseball backfill --start-season 2024 --end-season 2024 --force

# Full nightly cron cycle: ingest last N days + rebuild derived tables
baseball daily-update                # yesterday only
baseball daily-update --days 3       # catch up last 3 days
baseball daily-update --skip-rebuild # ingest only
```

The difference between `update` and `daily-update`: `update` pulls one day and stops. `daily-update` is the full cron cycle — it pulls the last N days, then rebuilds all derived tables so `matchup_edges` and the `_shrunk` columns reflect the fresh data. See **[deploy/README.md](deploy/README.md)** for VM deployment.

**Idempotency.** A sidecar `.manifest.json` at `data/raw/statcast/.manifest.json` tracks completed weeks. Re-running any command skips weeks that are already on disk. The cache is self-healing — if you delete a Parquet partition, the next run detects the missing file and re-pulls. Use `--force` to bypass the cache entirely.

**Rate limiting.** Pulls are chunked to one-week windows with a 0.5s sleep between weeks to be polite to Baseball Savant.

### Data layout

```
data/
├── raw/
│   └── statcast/
│       ├── season=2024/
│       │   ├── month=03/
│       │   │   └── pitches.parquet
│       │   ├── month=04/
│       │   │   └── pitches.parquet
│       │   └── ...
│       ├── season=2025/
│       └── .manifest.json              # completed-week tracker
├── derived/                            # rebuilt by `baseball rebuild-derived`
│   ├── pitcher_pitch_mix.parquet              # ✅ built
│   ├── pitcher_zone_tendency.parquet          # ✅ built
│   ├── pitcher_sequences_2pitch.parquet       # ✅ built
│   ├── batter_whiff_profile.parquet           # ✅ built
│   ├── batter_swing_decisions.parquet         # ✅ built
│   ├── batter_vs_sequences.parquet            # ✅ built
│   └── matchup_edges.parquet                  # ✅ built (+ `matchup_edges_top` view)
└── legacy/                             # frozen data for the legacy report
    └── *_starters_2025_*.parquet
```

The whole `data/raw/` and `data/derived/` tree is gitignored. `data/legacy/` is tracked for now so the legacy report works on a fresh clone.

### Expected disk usage

| Scope | Compressed size (ZSTD) |
|---|---|
| One week of Statcast (all pitches) | ~3.5 MB |
| One full season | ~120 MB |
| 2015 through 2026 (raw) | ~1.4 GB |
| Derived tables | ~200–400 MB |

Comfortably under the 8 GB VM budget.

### Schema

Raw Parquet partitions preserve every column `pybaseball.statcast()` returns (~118 columns). ID-like columns (`pitcher`, `batter`, `game_pk`, etc.) are cast to pandas nullable `Int64`; `game_date` is `datetime64`. No columns are dropped at ingest time.

### Querying

Data is exposed through **DuckDB**, an embedded SQL engine. Queries hit a `pitches` view that reads directly from `data/raw/statcast/**/*.parquet` — no load-into-database step. Any `data/derived/*.parquet` is auto-registered as a view named after its filename (so `pitcher_pitch_mix.parquet` becomes the `pitcher_pitch_mix` view).

Three ways to query, in increasing order of interactivity:

#### `baseball query` — one-off SQL

```bash
baseball query "SELECT COUNT(*) FROM pitches"
baseball query "SELECT player_name, COUNT(*) FROM pitches WHERE season=2024 GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
```

Returns up to 100 rows formatted as a table. Use this for scripting or quick spot-checks.

#### `baseball inspect` — diagnostics

```bash
baseball inspect --table pitches --season 2024
```

Prints row count, unique game count, date range, unique pitchers/batters, and null rates on key columns. Useful for verifying ingest completeness.

#### `baseball shell` — interactive prompt (recommended for exploration)

Think `psql`, but for DuckDB. Drops into a SQL prompt with all views pre-registered.

```
$ baseball shell
Connected. Tables: pitches
Type SQL (terminate with ;).  \d TABLE for schema, \dt for table list, \q to quit.

baseball> \dt
  pitches

baseball> \d pitches
   column_name     column_type  ...
     pitch_type         VARCHAR  ...
      game_date  TIMESTAMP_NS   ...
            ...

baseball> SELECT pitch_type, COUNT(*) AS n
       -> FROM pitches WHERE season=2024 AND game_type='R'
       -> GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
 pitch_type      n
         FF 225989
         SI 112095
         SL 106065
         CH  72240
         FC  58222

baseball> \q
```

Commands:

| Input | Effect |
|---|---|
| `SELECT ...;` | Run SQL — statements terminated by `;`, can span multiple lines |
| `\d TABLENAME` | Describe a table's schema (like `\d` in psql) |
| `\dt` | List all registered tables |
| `\q` / `exit` / `quit` / Ctrl-D | Exit the shell |
| Ctrl-C | Cancel the current multi-line buffer without exiting |

Command history and line editing work if the `readline` module is available (Unix default; on Windows install `pyreadline3` if you want arrow-key history).

#### `baseball rebuild-derived` — build derived Parquet tables

Aggregates the raw `pitches` into queryable summary tables under `data/derived/`. Each table is auto-registered as a view in subsequent `baseball query` / `baseball shell` sessions.

```bash
baseball rebuild-derived                                 # all tables in the registry
baseball rebuild-derived --table pitcher_pitch_mix        # just one
```

Current tables (regular season only):

**Pitcher tables:**

| Table | Key | Rows (2024) | What it answers |
|---|---|---|---|
| `pitcher_pitch_mix` | `(pitcher, season, balls, strikes, pitch_type)` | 35k | How often does this pitcher throw this pitch type in this count? |
| `pitcher_zone_tendency` | `(pitcher, season, pitch_type, balls, strikes, zone)` | 206k | Where does this pitcher locate this pitch type in this count? |
| `pitcher_sequences_2pitch` | `(pitcher, season, balls_before_p1, strikes_before_p1, pitch1_type, pitch2_type)` | 93k | When this pitcher throws X → Y, what's the whiff rate and put-away rate on Y? |

**Batter tables** (no name column — `batter` is the MLBAM ID; a lookup helper is coming in a later phase):

| Table | Key | Rows (2024) | What it answers |
|---|---|---|---|
| `batter_whiff_profile` | `(batter, season, pitch_type, zone, balls, strikes)` | 187k | Where does this batter whiff on which pitch types? |
| `batter_swing_decisions` | `(batter, season, balls, strikes)` | 7.6k | Chase% / z-swing% — does he expand the zone or take strikes? |
| `batter_vs_sequences` | `(batter, season, pitch1_type, pitch2_type)` | 41k | Batter outcomes on each 2-pitch sequence faced |

Every rate column ships in three flavors:
- **`_raw`** — empirical rate from the player's sample
- **`league_*`** — league rate at the same (pitch_type, zone, count) bucket
- **`_shrunk`** — empirical-Bayes blend of raw toward league, tuned per metric in `config.SHRINKAGE_K`

Every table also carries an explicit sample-size column (`pitch_count`, `zone_count`, `swings`, `n_sequences`, etc.) so consumers apply their own minimum thresholds. See `SAMPLE_SIZES.md` for recommended cutoffs.

**Matchup table:**

| Table | Key | Rows (2024) | What it answers |
|---|---|---|---|
| `matchup_edges` | `(pitcher, batter, season, pitch_type, balls, strikes)` | 3.85M | For every (pitcher, batter) pair that actually met: where's the leverage? |

Per-row columns include both sides' sample sizes, the batter's shrunk whiff rate, the league baseline, and two edge metrics:

- **`edge_lift`** = `batter_whiff_shrunk - league_whiff_rate` — the batter's excess vulnerability (independent of pitcher).
- **`edge_weighted`** = `pitcher_pct_shrunk × edge_lift` — leverage weighted by the pitcher actually throwing that pitch.

A convenience view **`matchup_edges_top`** is auto-registered alongside and rolls up to one row per `(pitcher, batter, season)` with the top-3 edges surfaced as columns. Good for building pairwise-matchup UIs without the frontend needing to aggregate.

```sql
-- Which pitches does Skubal hunt Juan Soto with?
SELECT pitch_type, balls, strikes, pitcher_n, batter_swings,
       ROUND(edge_lift*100, 1) AS lift_pp,
       ROUND(edge_weighted*1000, 1) AS weighted_x1000
FROM matchup_edges
WHERE player_name = 'Skubal, Tarik' AND batter = 665742
ORDER BY edge_weighted DESC LIMIT 5;
```

### DuckDB for Postgres users

If you're coming from Postgres, nearly everything transfers — CTEs, window functions, joins, aggregates, `CASE`, `EXTRACT()`, `DATE_TRUNC()`, identifier quoting, string concat with `||`. A few differences worth knowing:

| Task | Postgres | DuckDB |
|---|---|---|
| List tables | `\dt` | `SHOW TABLES` (or `\dt` inside `baseball shell`) |
| Describe table | `\d table` | `DESCRIBE table` (or `\d table` inside `baseball shell`) |
| Connection | TCP to a server | Embedded — no server, no port |
| Query a file | Foreign data wrapper / `COPY` | `SELECT * FROM read_parquet('*.parquet')` |
| Show settings | `SHOW ALL` | `SELECT * FROM duckdb_settings()` |

DuckDB-only tricks worth stealing:

- `SELECT * EXCLUDE (col_a, col_b) FROM t` — project everything *except* listed columns.
- `SELECT * REPLACE (CAST(x AS INT) AS x) FROM t` — swap a single column's value while keeping position.
- `read_parquet('dir/**/*.parquet', hive_partitioning=true)` — auto-extract `season=...` / `month=...` from paths into virtual columns (this is how our `pitches` view is built).
- `EXPLAIN ANALYZE <query>` works like Postgres.
- `SUMMARIZE table` — one-liner descriptive stats (min/max/avg/null-count) across every column.

Full DuckDB docs: https://duckdb.org/docs/

### Example validation queries

```sql
-- Pitch type distribution (regular season)
SELECT pitch_type, COUNT(*) AS n,
       COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS pct
FROM pitches WHERE season = 2024 AND game_type = 'R'
GROUP BY pitch_type ORDER BY n DESC;

-- Velo leaderboard, fastballs only, min 200 thrown
SELECT player_name, AVG(release_speed) AS avg_velo, COUNT(*) AS fastballs
FROM pitches
WHERE season = 2024 AND pitch_type IN ('FF','SI','FT') AND release_speed IS NOT NULL
GROUP BY player_name HAVING COUNT(*) > 200
ORDER BY avg_velo DESC LIMIT 20;

-- Whiff% by count (swings that miss / total swings)
SELECT balls || '-' || strikes AS count,
       SUM(CASE WHEN description = 'swinging_strike' THEN 1 ELSE 0 END) * 1.0 /
       NULLIF(SUM(CASE WHEN description IN ('swinging_strike','foul','foul_tip','hit_into_play') THEN 1 ELSE 0 END), 0) AS whiff_rate,
       COUNT(*) AS pitches
FROM pitches WHERE season = 2024 AND game_type = 'R'
GROUP BY 1 ORDER BY 1;

-- Sanity: row counts by (season, month) to confirm partition coverage
SELECT season, month, COUNT(*) AS n FROM pitches GROUP BY 1, 2 ORDER BY 1, 2;
```

## Legacy web app

The first-pitch offspeed CSW% / whiff% report lives at `reports/first_pitch_offspeed/` and is served by a FastAPI backend + React frontend. It runs against frozen per-division Parquet in `data/legacy/` and is unaffected by the new pipeline.

```bash
# Backend (terminal 1)
python -m uvicorn backend.main:app --reload --port 8000

# Frontend (terminal 2)
cd frontend
npm install
npm run dev
```

UI on http://localhost:5173, interactive API docs on http://localhost:8000/docs.

## Reports

`reports/` is a blog-style archive of standalone analyses. Each report is self-contained and does not share data infrastructure with the main pipeline — think of it as a place for one-off deep dives and historical artifacts.

Current reports:

- **First-pitch offspeed** (`reports/first_pitch_offspeed/`) — do hard throwers (96+ mph fastball) get more whiffs / CSW% when leading an at-bat with an offspeed pitch than soft throwers?

## Development

### Tests

```bash
pytest tests/ -v
```

### Lint / format

```bash
ruff check src/ tests/
ruff format src/ tests/
# or
black src/ tests/
```

### Configuration

All settings live in `.env` (copy from `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `BASEBALL_LOG_LEVEL` | `INFO` | loguru level |
| `BASEBALL_DUCKDB_MEMORY_LIMIT` | unset | Memory cap for DuckDB (e.g. `4GB` on the 8 GB VM) |
| `BASEBALL_DATA_ROOT` | `./data` | Override data directory (e.g. mounted disk) |

### Sample-size conventions

See **[SAMPLE_SIZES.md](SAMPLE_SIZES.md)** for the minimum-sample thresholds and empirical-Bayes shrinkage approach used by derived tables. The short version: we store every sample in derived tables without filtering, and thresholds / shrinkage are applied at query time.

## Deployment (nightly cron on a VM)

The full cycle — **ingest yesterday + rebuild derived tables** — is wrapped up in `baseball daily-update`. Templates for both **systemd timer** (recommended, DST-aware) and **crontab** (simpler, UTC only) live in the `deploy/` directory.

Quickstart on a fresh Linux VM:

```bash
git clone <repo-url> /opt/baseball
cd /opt/baseball
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .
.venv/bin/baseball backfill --start-season 2015 --end-season $(date +%Y)
.venv/bin/baseball rebuild-derived

# Systemd timer (recommended)
sudo useradd --system --create-home --shell /usr/sbin/nologin baseball
sudo mkdir -p /var/log/baseball
sudo chown -R baseball:baseball /opt/baseball /var/log/baseball
sudo cp deploy/systemd/baseball-daily-update.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now baseball-daily-update.timer
```

See **[deploy/README.md](deploy/README.md)** for the full walkthrough, crontab alternative, troubleshooting, and environment-variable knobs (memory cap, log directory).

## Project structure

```
src/baseball/
├── config.py               # paths, pydantic settings
├── cli.py                  # typer app (`baseball` entry point)
├── ingest/
│   ├── statcast.py         # chunked pybaseball pulls + partitioned writes
│   └── backfill.py         # season iteration over ingest
├── storage/
│   └── duckdb_conn.py      # DuckDB connection factory + view registration
├── derived/
│   ├── _common.py          # shared helper: write_derived_parquet
│   ├── pitcher_tables.py   # pitch_mix, zone_tendency, sequences_2pitch
│   ├── batter_tables.py    # whiff_profile, swing_decisions, vs_sequences
│   └── matchup_tables.py   # matchup_edges + matchup_edges_top view
└── jobs/
    ├── rebuild_derived.py  # REGISTRY + rebuild orchestrator
    └── daily_update.py     # cron entrypoint: ingest + rebuild

deploy/                     # systemd unit + crontab templates for VM install
├── README.md
├── crontab.example
└── systemd/
    ├── baseball-daily-update.service
    └── baseball-daily-update.timer

reports/                    # standalone analyses (see Reports section)
backend/                    # legacy FastAPI
frontend/                   # legacy React + Vite
tests/
data/                       # gitignored (except data/legacy/)
```
