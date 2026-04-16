# MLB Whiff Percentage

Streamlit app that analyzes whether MLB starters who average 96+ mph on their
fastball get a higher whiff rate when leading an at-bat with an offspeed pitch
than pitchers who don't reach 96.

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

Each run writes two CSVs per division:

- `{division}_starters_2025_roster.csv` — one row per starting pitcher
- `{division}_starters_2025_pitches.csv` — one row per pitch

Statcast pulls can take several minutes per division. `pybaseball`'s cache is
enabled, so re-runs are faster.

## Running the app

```bash
streamlit run app.py
```

Streamlit prints a local URL (typically http://localhost:8501) — open it in a
browser. Use the sidebar to pick divisions and toggle filters (velo threshold,
IVB, minimum pitches, etc.).

### `streamlit: command not found` / `'streamlit' is not recognized`

If the `streamlit` command isn't on your PATH, run it as a Python module
instead — this works on any platform:

```bash
python -m streamlit run app.py
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

`analyze_pitches.py` can also be imported directly for ad-hoc analysis:

```python
from analyze_pitches import compute_buckets, available_divisions

print(available_divisions())
print(compute_buckets(divisions=["nl_east", "al_east"]))
```

## Project layout

```
Python-MLB-Whiff_Percentage/
├── app.py                 # Streamlit UI
├── analyze_pitches.py     # Bucketing / whiff-rate logic
├── fetch_starters.py      # Statcast data pull
├── requirements.txt
└── *_starters_2025_*.csv  # Cached Statcast data
```
