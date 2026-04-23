# MLB Pitch Analytics

Web app for exploring MLB pitch-data hypotheses. Each "report" is a
self-contained analysis under `reports/`, exposed through a FastAPI backend
and rendered by a React frontend.

Current reports:

- **First-pitch offspeed (CSW% & whiff%)** — do hard-throwing starters
  (96+ mph fastball) generate more CSW% or whiffs when leading an at-bat
  with an offspeed pitch than soft throwers? Splits by velo and 4-seam vs.
  offspeed vertical separation.

  - **CSW%** = (called strikes + whiffs) / total pitches
  - **Whiff %** = whiffs / total swings

Data comes from Baseball Savant (Statcast), pulled via `pybaseball`.

## Architecture

```
├── backend/                         # FastAPI app (thin HTTP shell)
│   └── main.py
├── frontend/                        # React + Vite UI
│   └── src/
├── reports/
│   └── first_pitch_offspeed/
│       └── analyze.py               # Pure-pandas analysis logic
├── fetch_starters.py                # Statcast data pull
├── data/                            # Cached Parquet files
└── requirements.txt                 # Python deps
```

The analysis logic in `reports/*/analyze.py` has no web dependencies — the
backend just wraps it in HTTP endpoints, and the frontend calls those
endpoints.

## Setup

### Backend (Python 3.9+)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Frontend (Node 18+)

```bash
cd frontend
npm install
```

## Fetching data

The repo ships with cached Parquet files for all six divisions (2025 season).
To refresh or pull additional divisions:

```bash
python fetch_starters.py nl_east      # single division
python fetch_starters.py all          # every division
```

Valid divisions: `al_east`, `al_central`, `al_west`, `nl_east`, `nl_central`,
`nl_west`. Each run writes two Parquet files per division into `data/`.

## Running the app

Open two terminals.

**Terminal 1 — backend:**

```bash
uvicorn backend.main:app --reload --port 8000
```

API will be on http://localhost:8000 (interactive docs at
http://localhost:8000/docs).

**Terminal 2 — frontend:**

```bash
cd frontend
npm run dev
```

Vite serves the UI on http://localhost:5173 and proxies `/api/*` to the
backend. Open that URL in the browser.

## API endpoints

| Method | Path                                 | Purpose                        |
| ------ | ------------------------------------ | ------------------------------ |
| GET    | `/api/reports`                       | Catalog used by the home page  |
| GET    | `/api/divisions`                     | Cached divisions on disk       |
| GET    | `/api/first-pitch-offspeed/meta`     | Pitch-type labels + constants  |
| POST   | `/api/first-pitch-offspeed/compute`  | Full result payload (filtered) |

## Command-line analysis

Each report's `analyze.py` can be imported or run directly:

```python
from reports.first_pitch_offspeed.analyze import compute, available_divisions

print(available_divisions())
print(compute(divisions=["nl_east", "al_east"]))
```

```bash
python -m reports.first_pitch_offspeed.analyze nl_east al_west
```

## Adding a new report

1. Create `reports/<your_report>/` with `__init__.py` and `analyze.py`. Use
   `first_pitch_offspeed/` as a template — keep it pure pandas, no web deps.
2. Read cached Parquet from `Path(__file__).resolve().parents[2] / "data"`.
3. Add endpoints for it in `backend/main.py` (mirror the
   `first-pitch-offspeed` pattern).
4. Add an entry to the `REPORTS` list in `backend/main.py` so the home page
   links to it, and build a page under `frontend/src/pages/` plus a matching
   route in `frontend/src/App.jsx`.

# Future Ideas

- Separate the pitches into less broad categories
   - Instead of just offspeed we could do:
      - Glove side movement: pitches that break towards the pitchers glove side (Slider, Sweeper, Curve, Slurve)
      - Velocity disruption: Fastball "decoy" pitches (Changeup, Forkball, Splitter)
- Pitcher leaderboards for specific categories like the ones above
- Per-player pages (one URL per pitcher) and search
