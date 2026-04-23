# MLB Pitch Analytics Platform

Data infrastructure + interactive web UI for MLB pitch-sequencing and pitcher/batter matchup edges. Pulls Statcast via `pybaseball`, aggregates into DuckDB-queryable derived tables, and surfaces two analyzers on top:

- **Pitch-sequence analyzer** — every 2-pitch combo a pitcher throws (or a batter faces), with empirical-Bayes shrinkage and league comparison.
- **Matchup edges** — pitcher tendency × batter vulnerability per (pitch, count). Finds the single highest-leverage pitch in any pitcher-batter matchup.

---

## Quickstart

### 1. One-time setup

```bash
git clone <repo-url>
cd Python-MLB-Whiff_Percentage

python -m venv .venv
# activate — pick the line for your shell:
source .venv/bin/activate            # macOS / Linux / Git Bash
.venv\Scripts\Activate.ps1           # Windows PowerShell

pip install -r requirements.txt
pip install -e .                     # registers the `baseball` CLI
```

Populate data (takes ~30 min for full history; pick a single season if you just want to test):

```bash
baseball backfill --start-season 2024 --end-season 2024    # single season (~5 min)
baseball backfill --start-season 2015 --end-season 2026    # full history (~1 hour)
baseball rebuild-derived
```

### 2. Run locally

Two terminals:

```bash
# terminal 1 — API
python -m uvicorn backend.main:app --reload --port 8000

# terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Interactive API docs at http://localhost:8000/docs.

### 3. Or — frontend against the deployed VM

If you don't want to start uvicorn locally (or you don't have the data backfilled), the frontend can proxy to the production VM API instead:

```bash
cd frontend
npm run dev:vm
```

No backend needed on your laptop.

### Things to try

- **Sequences → Pitcher view**: pick Skubal, pitch1 FF, pitch2 CH, count 0-2 → his ~2.5× league putaway edge.
- **Sequences → Batter view**: pick Juan Soto, sort by "Whiff lift vs league" → surfaces his worst sequences.
- **Matchup**: pick Skubal + Soto → best edge CH in 1-2. Toggle perspective to "Batter" to see Soto's best spots.
- **Ad-hoc SQL**: `baseball shell` drops into a psql-like prompt with every table pre-registered.

### Further reading

- **[TABLES.md](TABLES.md)** — plain-English guide to every table & column (start here if you're new to the data).
- **[SAMPLE_SIZES.md](SAMPLE_SIZES.md)** — minimum-sample conventions and empirical-Bayes shrinkage.
- **[deploy/README.md](deploy/README.md)** — VM deployment walkthrough.

---

## CLI reference

The `baseball` command group (installed by `pip install -e .`):

| Command | Purpose |
|---|---|
| `baseball backfill --start-season S --end-season E` | one-time historical Statcast pull |
| `baseball update [--date YYYY-MM-DD]` | single-day ingest (defaults to yesterday) |
| `baseball daily-update [--days N]` | cron entrypoint: ingest last N days + rebuild |
| `baseball rebuild-derived [--table T]` | recompute derived Parquet tables |
| `baseball inspect --table T [--season S]` | row counts, date range, null rates |
| `baseball query "SELECT ..."` | one-off SQL against the data |
| `baseball shell` | interactive SQL prompt |

Run `baseball <cmd> --help` for flags.

**Idempotency.** `data/raw/statcast/.manifest.json` tracks completed weeks — re-running any command skips work already done. Pass `--force` to bypass.

**Rate limiting.** Pulls are chunked one week at a time with a 0.5s sleep between weeks, out of respect for Baseball Savant.

**`update` vs `daily-update`.** `update` pulls one day and stops. `daily-update` is the full cron cycle — pulls the last N days, then rebuilds all derived tables so `matchup_edges` and the `_shrunk` columns reflect the fresh data.

---

## Data pipeline

### Layout

```
data/
├── raw/statcast/
│   ├── season=2024/month=03/pitches.parquet
│   ├── season=2024/month=04/pitches.parquet
│   └── .manifest.json                    # completed-week tracker
├── derived/                              # rebuilt by `baseball rebuild-derived`
│   ├── pitcher_pitch_mix.parquet
│   ├── pitcher_zone_tendency.parquet
│   ├── pitcher_sequences_2pitch.parquet
│   ├── batter_whiff_profile.parquet
│   ├── batter_swing_decisions.parquet
│   ├── batter_vs_sequences.parquet
│   └── matchup_edges.parquet             # + `matchup_edges_top` view
└── legacy/                               # frozen data for the legacy FPO report
    └── *_starters_2025_*.parquet
```

`data/raw/` and `data/derived/` are gitignored; `data/legacy/` is tracked so the legacy report runs on a fresh clone.

### Disk usage

| Scope | Compressed (ZSTD) |
|---|---|
| One week of Statcast | ~3.5 MB |
| One full season | ~120 MB |
| 2015 – 2026 raw | ~1.4 GB |
| Derived tables | ~200–400 MB |

### Schema

Raw Parquet preserves every column `pybaseball.statcast()` returns (~118). ID-like columns are cast to pandas nullable `Int64`; `game_date` is `datetime64`. No columns dropped at ingest.

### Querying

Data is exposed via **DuckDB** — embedded, no server. A `pitches` view reads `data/raw/statcast/**/*.parquet` directly (no load step). Every `data/derived/*.parquet` auto-registers as a view named after its filename.

`baseball shell` drops into a psql-style prompt:

```
baseball> \dt
  pitches
  pitcher_pitch_mix
  matchup_edges
  ...

baseball> SELECT pitch_type, COUNT(*) n
       -> FROM pitches WHERE season=2024 AND game_type='R'
       -> GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
```

Commands: `\dt` list tables · `\d TABLE` describe · `\q` / Ctrl-D exit · Ctrl-C cancel multi-line buffer.

---

## Derived tables

Seven tables from `rebuild-derived`. Regular season only. See [TABLES.md](TABLES.md) for full column-by-column docs.

**Pitcher tables**

| Table | Key | What it answers |
|---|---|---|
| `pitcher_pitch_mix` | `(pitcher, season, balls, strikes, pitch_type)` | How often does this pitcher throw this pitch in this count? |
| `pitcher_zone_tendency` | `(pitcher, season, pitch_type, balls, strikes, zone)` | Where does he locate it? |
| `pitcher_sequences_2pitch` | `(pitcher, season, balls_before_p1, strikes_before_p1, pitch1_type, pitch2_type)` | On X → Y, what's the whiff rate and put-away rate on Y? |

**Batter tables** (batter column is MLBAM ID; names via Chadwick Bureau at API level)

| Table | Key | What it answers |
|---|---|---|
| `batter_whiff_profile` | `(batter, season, pitch_type, zone, balls, strikes)` | Where does this batter whiff? |
| `batter_swing_decisions` | `(batter, season, balls, strikes)` | Chase% / z-swing% |
| `batter_vs_sequences` | `(batter, season, pitch1_type, pitch2_type)` | Outcomes on each 2-pitch sequence faced |

**Matchup table**

| Table | Key | What it answers |
|---|---|---|
| `matchup_edges` | `(pitcher, batter, season, pitch_type, balls, strikes)` | For every pair that met: where's the leverage? |

Plus the `matchup_edges_top` view — one row per pair, top-3 edges surfaced as columns (ready for UI consumption).

**Rate columns ship three ways:** `_raw` (empirical), `league_*` (league baseline at the same bucket), `_shrunk` (empirical-Bayes blend, tuned per metric in `config.SHRINKAGE_K`). Every table also carries an explicit sample-size column. Apply minimum thresholds at query time — see [SAMPLE_SIZES.md](SAMPLE_SIZES.md).

**Edge metrics:**

- **`edge_lift`** = `batter_whiff_shrunk - league_whiff_rate` — batter's excess vulnerability, pitcher-independent.
- **`edge_weighted`** = `pitcher_pct_shrunk × edge_lift` — leverage, only big when the pitcher actually throws the pitch.

---

## API v2

All endpoints for the analyzer UI live under `/api/v2/*` in `backend/v2/`. They read the derived Parquet via a single long-lived DuckDB connection opened at app startup. No caching layer — DuckDB over Parquet is sub-100ms.

Interactive docs: http://localhost:8000/docs (dev) · `http://<vm-ip>:8000/docs` (deployed).

**Lookups (dropdowns)**

| Endpoint | Purpose |
|---|---|
| `GET /api/v2/seasons` | seasons available |
| `GET /api/v2/pitch-types` | codes + human labels |
| `GET /api/v2/pitchers?season&q&limit` | type-ahead pitcher search |
| `GET /api/v2/batters?season&q&limit` | type-ahead batter search (Chadwick-backed) |

**Pitch-sequence analyzer**

| Endpoint | Purpose |
|---|---|
| `GET /api/v2/sequences/pitcher/{id}` | one pitcher's combos, filterable by `season`, `balls`, `strikes`, `pitch1`, `pitch2`, `min_n`, `sort`, `limit` |
| `GET /api/v2/sequences/batter/{id}` | one batter's combos (rolled up across counts) |
| `GET /api/v2/sequences/leaderboard?pitch1&pitch2&season&role&balls&strikes&min_n&limit` | top players on a specific sequence |

**Matchup edges**

| Endpoint | Purpose |
|---|---|
| `GET /api/v2/matchup/pairing/{pitcher_id}/{batter_id}?season` | scouting card for one pair |
| `GET /api/v2/matchup/edges/top?season&pitcher_id&batter_id&pitch_type&balls&strikes&min_pitcher_n&min_batter_swings&sort&perspective&limit` | general-purpose top-N; `perspective=pitcher` (default) or `batter` flips the sort direction |

**Batter names.** The derived tables only store batter MLBAM IDs. On first API startup, `/api/v2/batters` fetches Chadwick Bureau's public register via `pybaseball.chadwick_register()` and caches a trimmed lookup to `data/player_names.parquet` (~1 MB, ~4s to build, gitignored). If the fetch fails, batter endpoints fall back to `id:665742`-style labels.

---

## Frontend (React)

`frontend/` is a Vite + React app. `/api/*` requests are proxied server-side to whichever backend the selected mode points at — the browser always thinks it's same-origin with `localhost:5173`, so no CORS setup.

**Switching between local and VM backend**

| Command | Proxy target | Need local uvicorn? |
|---|---|---|
| `npm run dev` | `http://127.0.0.1:8000` (from `.env.development`) | **Yes** |
| `npm run dev:vm` | VM (from `.env.vm`) | No |

Env-file precedence (later wins): `.env` → `.env.local` → `.env.[mode]` → `.env.[mode].local`. The mode files (`.env.development`, `.env.vm`) override any `.env.local`, so you can leave a `.env.local` in place for one-off overrides (a colleague's VM, a staging box) without worrying about it bleeding into the normal scripts.

**If the VM IP rotates** — edit `frontend/.env.vm` and commit.

---

## Deployment (Oracle VM)

Nightly cron and the API both run on the same Ubuntu 24.04 ARM VM. See [deploy/README.md](deploy/README.md) for the full walkthrough; quickstart summary below.

### Nightly cron (ingest + rebuild)

Templates for **systemd timer** (recommended, DST-aware) and **crontab** (simpler, UTC only) live in `deploy/`.

```bash
git clone <repo-url> /opt/baseball
cd /opt/baseball
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .
.venv/bin/baseball backfill --start-season 2015 --end-season $(date +%Y)
.venv/bin/baseball rebuild-derived

# systemd timer
sudo cp deploy/systemd/baseball-daily-update.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now baseball-daily-update.timer
```

### API service (FastAPI)

The FastAPI app runs as a long-lived systemd service — auto-starts on boot, auto-restarts on crash.

```bash
sudo tee /etc/systemd/system/mlb-api.service > /dev/null <<'EOF'
[Unit]
Description=MLB Pitch Analytics API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/baseball
Environment=BASEBALL_LOG_LEVEL=INFO
ExecStart=/opt/baseball/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload && sudo systemctl enable --now mlb-api.service
```

### Opening port 8000 (OCI)

Two layers, both required:

```bash
# 1. Host firewall — insert BEFORE the REJECT line; verify with `sudo iptables -L INPUT --line-numbers`
sudo iptables -I INPUT 5 -p tcp --dport 8000 -j ACCEPT
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

```
# 2. OCI console — Networking → VCN → Security Lists → Default → Add Ingress Rules
#    Source: 0.0.0.0/0, TCP, port 8000
```

### Daily ops

After `git push` from your laptop:

```bash
ssh ubuntu@<vm-ip>
cd /opt/baseball && git pull
sudo systemctl restart mlb-api

# logs
journalctl -u mlb-api -n 50 --no-pager      # recent
journalctl -u mlb-api -f                    # follow
sudo systemctl status mlb-api --no-pager
```

**Deferred for prod.** Plain HTTP on port 8000 is fine for backend dev. Before a real public launch, wire up Caddy for TLS and add the production origin to `CORSMiddleware` in `backend/main.py`.

---

## Development

### Tests

```bash
pytest tests/ -v
```

### Lint / format

```bash
ruff check src/ tests/
ruff format src/ tests/
```

### Configuration

All settings in `.env` (copy from `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `BASEBALL_LOG_LEVEL` | `INFO` | loguru level |
| `BASEBALL_DUCKDB_MEMORY_LIMIT` | unset | DuckDB memory cap (e.g. `4GB` on the 8 GB VM) |
| `BASEBALL_DATA_ROOT` | `./data` | override data directory |

---

## Reference

### Reports

`reports/` is an archive of standalone one-off analyses, separate from the main pipeline. Currently one:

- **First-pitch offspeed** (`reports/first_pitch_offspeed/`) — do hard throwers (96+ mph fastball) get more CSW% / whiffs leading at-bats with an offspeed pitch than soft throwers? Serves from frozen per-division Parquet in `data/legacy/` via the legacy `/api/first-pitch-offspeed/*` endpoints.

### DuckDB for Postgres users

Nearly everything transfers — CTEs, window functions, joins, aggregates, `CASE`, `EXTRACT()`, `DATE_TRUNC()`, identifier quoting, `||` concat. Differences:

| Task | Postgres | DuckDB |
|---|---|---|
| List tables | `\dt` | `SHOW TABLES` (or `\dt` in `baseball shell`) |
| Describe table | `\d table` | `DESCRIBE table` (or `\d table` in `baseball shell`) |
| Connection | TCP to a server | Embedded — no server, no port |
| Query a file | FDW / `COPY` | `SELECT * FROM read_parquet('*.parquet')` |

DuckDB-only tricks worth stealing:

- `SELECT * EXCLUDE (col_a, col_b) FROM t` — project everything except those.
- `SELECT * REPLACE (CAST(x AS INT) AS x) FROM t` — swap a single column's value in place.
- `read_parquet('dir/**/*.parquet', hive_partitioning=true)` — auto-extract `season=.../month=...` from paths.
- `SUMMARIZE table` — one-liner descriptive stats across every column.

Full docs: https://duckdb.org/docs/

### Example validation queries

```sql
-- Pitch type distribution (regular season)
SELECT pitch_type, COUNT(*) n, COUNT(*)*100.0/SUM(COUNT(*)) OVER () pct
FROM pitches WHERE season=2024 AND game_type='R'
GROUP BY 1 ORDER BY 2 DESC;

-- Velo leaderboard, fastballs only, min 200 thrown
SELECT player_name, AVG(release_speed) velo, COUNT(*) n
FROM pitches
WHERE season=2024 AND pitch_type IN ('FF','SI') AND release_speed IS NOT NULL
GROUP BY player_name HAVING COUNT(*) > 200
ORDER BY velo DESC LIMIT 20;

-- Sanity: row counts by partition
SELECT season, month, COUNT(*) n FROM pitches GROUP BY 1,2 ORDER BY 1,2;
```

### Project structure

```
src/baseball/
├── config.py               # paths, pydantic settings, shrinkage constants
├── cli.py                  # typer app (`baseball` entry point)
├── ingest/                 # chunked pybaseball pulls + partitioned writes
├── storage/duckdb_conn.py  # connection factory + view registration
├── derived/                # pitch_mix, zone_tendency, sequences, whiff_profile, matchup_edges
└── jobs/
    ├── rebuild_derived.py  # registry + orchestrator
    └── daily_update.py     # cron entrypoint

backend/                    # FastAPI — legacy /api/* + new /api/v2/*
├── main.py
└── v2/                     # sequences, matchup, lookups, player_names

frontend/                   # Vite + React — analyzer pages + legacy report
deploy/                     # systemd units + crontab templates for VM
reports/                    # standalone one-off analyses
tests/
data/                       # gitignored (except data/legacy/)
```
