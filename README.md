# MLB Pitch Analytics

Streamlit app for exploring MLB pitch-data hypotheses. Each "report" is a
self-contained analysis under `reports/`, surfaced through a shared home page
with sidebar navigation.

Current reports:

- **First-pitch offspeed (CSW% & whiff%)** — do hard-throwing starters
  (96+ mph fastball) generate more CSW% or whiffs when leading an at-bat
  with an offspeed pitch than soft throwers? Splits by velo and 4-seam vs.
  offspeed vertical separation. Both metrics are shown in every roster
  row; a sidebar toggle picks which one drives the headline cards, the
  bucket Δ, and the scatter plot.

  - **CSW%** = (called strikes + whiffs) / total pitches
  - **Whiff %** = whiffs / total swings

Data comes from Baseball Savant (Statcast), pulled via `pybaseball`.

## Setup

Requires Python 3.9+.

```bash
# 1. Clone / enter the project directory
cd Python-MLB-Whiff_Percentage

# 2. (Recommended) create a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

## Fetching data

The repo ships with cached CSVs for all six divisions (2025 season). To refresh
or pull additional divisions, run:

```bash
python fetch_starters.py nl_east      # single division
python fetch_starters.py all          # every division
```

Valid divisions: `al_east`, `al_central`, `al_west`, `nl_east`, `nl_central`,
`nl_west`.

Each run writes two CSVs per division into `data/`:

- `data/{division}_starters_2025_roster.csv` — one row per starting pitcher
- `data/{division}_starters_2025_pitches.csv` — one row per pitch

All reports read from `data/`, so a single fetch feeds every analysis.
Statcast pulls can take several minutes per division. `pybaseball`'s cache is
enabled, so re-runs are faster.

## Running the app

```bash
streamlit run home.py
```

Streamlit prints a local URL (typically http://localhost:8501). The home page
lists every available report; pick one from the sidebar or click a card. Each
report has its own filters in the sidebar.

### `streamlit: command not found` / `'streamlit' is not recognized`

If the `streamlit` command isn't on your PATH, run it as a Python module
instead — this works on any platform:

```bash
python -m streamlit run home.py
```

If that also fails with `No module named streamlit`, the dependencies aren't
installed into the Python you're using. Check:

1. The virtual environment is activated (your shell prompt should show
   `(.venv)`). On Windows: `.venv\Scripts\activate`. On macOS/Linux:
   `source .venv/bin/activate`.
2. `pip install -r requirements.txt` was run **after** activating the venv.
3. `pip` and `python` resolve to the same interpreter — verify with
   `python -m pip list | grep streamlit` (or `findstr streamlit` on Windows).

## Command-line analysis

Each report's `analyze.py` can be imported directly for ad-hoc work:

```python
from reports.first_pitch_offspeed.analyze import compute_buckets, available_divisions

print(available_divisions())
print(compute_buckets(divisions=["nl_east", "al_east"]))
```

Or run it as a module from the project root:

```bash
python -m reports.first_pitch_offspeed.analyze nl_east al_west
```

## Project layout

```
├── home.py                          # Streamlit entry point + navigation
├── fetch_starters.py                # Shared Statcast data pull
├── data/                            # Shared cached CSVs (one set per division)
├── reports/
│   └── first_pitch_offspeed/
│       ├── analyze.py               # Bucketing / whiff-rate logic
│       └── page.py                  # Streamlit UI for this report
└── requirements.txt
```

## Adding a new report

1. Create `reports/<your_report>/` with `__init__.py`, `analyze.py`, and
   `page.py`. Use `first_pitch_offspeed/` as a template.
2. In `analyze.py`, read CSVs from the shared `data/` folder via
   `Path(__file__).resolve().parents[2] / "data"`.
3. In `page.py`, import from your analyze module with the absolute path
   `from reports.<your_report>.analyze import ...`.
4. Add an entry to the `REPORTS` list in `home.py` — the home page renders a
   card and the sidebar gets a nav link automatically.

# Future Ideas

- Separate the pitches into less broad categories
   - Instead of just offspeed we could do:
      - Glove side movement: pitches that break towards the pitchers glove side (Slider, Sweeper, Curve, Slurve)
      - Velocity disruption: Fastball "decoy" pitches (Changeup, Forkball, Splitter)
- Pitcher leaderboards for specific categories like the ones above