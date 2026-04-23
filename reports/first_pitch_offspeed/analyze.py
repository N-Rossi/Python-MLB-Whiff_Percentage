"""
Question: Do pitchers who average 96+ mph on the fastball get a higher
whiff rate when leading an at-bat with an offspeed pitch than pitchers
who don't reach 96?

Reads every cached CSV produced by fetch_starters.py and concatenates
them. Pass `divisions=[...]` to compute_buckets() to limit the scope.
"""

from pathlib import Path
import re

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PITCHES_GLOB = "*_starters_*_pitches.parquet"

# Statcast pitch_type codes
# Cutter (FC) is excluded from "fastball" for velocity-bucketing because it
# typically sits 5+ mph slower than 4-seam and would unfairly drag pitchers
# under 96.
FASTBALL_TYPES = {"FF", "SI", "FT"}

# "Offspeed" here means everything that isn't a fastball/cutter — the broad
# colloquial sense (breaking balls + true offspeed). Narrow this to
# {"CH", "FS", "FO", "SC"} if you want changeup-family only.
NON_OFFSPEED = FASTBALL_TYPES | {"FC"}

# Match the swing/whiff definition already used in pitches.py
SWING_DESCRIPTIONS = {
    "swinging_strike", "swinging_strike_blocked",
    "foul", "foul_tip", "hit_into_play",
}

# Statcast description for a taken strike. Used in the CSW% numerator.
CALLED_STRIKE_DESCRIPTION = "called_strike"


_DIVISION_FROM_FILENAME = re.compile(r"^(.+?)_starters_\d+_pitches\.parquet$")


def available_divisions():
    """Return a sorted list of divisions that have a cached pitches CSV."""
    divs = []
    for path in sorted(DATA_DIR.glob(PITCHES_GLOB)):
        m = _DIVISION_FROM_FILENAME.match(path.name)
        if m:
            divs.append(m.group(1))
    return sorted(set(divs))


_PITCH_CACHE = {}  # (path, mtime_ns) -> DataFrame (one entry per file)
_CONCAT_CACHE = {}  # (frozenset(paths+mtimes), divisions) -> concatenated DataFrame


def _load_one(path):
    """Read one parquet file, cached by (path, mtime). The Parquet read is the
    slow part, so the cache bypasses it on every subsequent request."""
    m = _DIVISION_FROM_FILENAME.match(path.name)
    div = m.group(1) if m else path.stem
    key = (str(path), path.stat().st_mtime_ns)
    hit = _PITCH_CACHE.get(key)
    if hit is not None:
        return div, hit
    df = pd.read_parquet(path)
    if "division" not in df.columns:
        df["division"] = div
    _PITCH_CACHE[key] = df
    # Drop any older cache entries for the same file (different mtime).
    stale = [k for k in _PITCH_CACHE if k[0] == str(path) and k != key]
    for k in stale:
        _PITCH_CACHE.pop(k, None)
    return div, df


def load_pitches(divisions=None):
    """
    Load and concat every {division}_starters_*_pitches.parquet in the data
    dir. If `divisions` is given, restrict to those. Adds/repairs the
    `division` column from the filename for older files that predate it.

    Cached in memory per file — first call is slow, subsequent calls are fast.
    """
    paths = sorted(DATA_DIR.glob(PITCHES_GLOB))
    if not paths:
        raise FileNotFoundError(
            f"No pitch parquet files found in {DATA_DIR}. "
            f"Run `python fetch_starters.py <division>` first."
        )

    file_fingerprint = frozenset(
        (str(p), p.stat().st_mtime_ns) for p in paths
    )
    divs_key = frozenset(divisions) if divisions else None
    cache_key = (file_fingerprint, divs_key)
    hit = _CONCAT_CACHE.get(cache_key)
    if hit is not None:
        return hit

    frames = []
    for path in paths:
        div, df = _load_one(path)
        if divisions and div not in divisions:
            continue
        frames.append(df)

    if not frames:
        raise FileNotFoundError(
            f"No pitch parquet files matched divisions={divisions}. "
            f"Available: {available_divisions()}"
        )
    combined = pd.concat(frames, ignore_index=True)
    _CONCAT_CACHE.clear()  # bound memory: only keep the most recent cut
    _CONCAT_CACHE[cache_key] = combined
    return combined


def _pitch_stats(d):
    pitches = len(d)
    swings = d[d["description"].isin(SWING_DESCRIPTIONS)]
    whiffs = swings[swings["description"].str.startswith("swinging_strike")]
    called = d[d["description"] == CALLED_STRIKE_DESCRIPTION]
    n_swings, n_whiffs, n_called = len(swings), len(whiffs), len(called)
    return {
        "pitches": pitches,
        "swings": n_swings,
        "whiffs": n_whiffs,
        "called_strikes": n_called,
        "whiff_rate": round(n_whiffs / n_swings * 100, 1) if n_swings else None,
        "csw_rate": round((n_called + n_whiffs) / pitches * 100, 1) if pitches else None,
    }


# Statcast offspeed pitch_type codes → human-readable labels. Drives the
# sidebar multiselect, the per-pitch detail filter, and the abbreviation key
# rendered under the detail filters.
PITCH_TYPE_LABELS = {
    "SL": "Slider",
    "ST": "Sweeper",
    "SV": "Slurve",
    "CH": "Changeup",
    "CU": "Curveball",
    "KC": "Knuckle-curve",
    "CS": "Slow curve",
    "FS": "Splitter",
    "FO": "Forkball",
    "SC": "Screwball",
    "KN": "Knuckleball",
    "EP": "Eephus",
}
OFFSPEED_PITCH_TYPES = tuple(PITCH_TYPE_LABELS.keys())


def _build_pitch_details(d, name_map, team_map, velo_dict, vsep_dict):
    """
    One row per first-pitch offspeed pitch (already filtered by the caller).
    Vectorized: build all output columns, then `to_dict('records')` once.
    """
    if d.empty:
        return []

    sort_cols = [c for c in ("pitcher", "game_date", "at_bat_number") if c in d.columns]
    if sort_cols:
        d = d.sort_values(sort_cols)

    pid = d["pitcher"]
    desc = d["description"]
    out = pd.DataFrame({
        "pitcher_id": pid.astype("int64"),
        "pitcher": pid.map(name_map).fillna(pid.astype(str)),
        "team": pid.map(team_map),
        "game_date": d["game_date"].astype(str) if "game_date" in d.columns else None,
        "velo": pid.map(velo_dict).astype("Float64"),
        "vsep": pid.map(vsep_dict).astype("Float64"),
        "pitch_type": d["pitch_type"],
        "p_throws": d["p_throws"],
        "stand": d["stand"],
        "in_zone": d["in_zone"],
        "same_hand": d["same_hand"],
        "description": desc,
        "swing": desc.isin(SWING_DESCRIPTIONS).astype("int8"),
        "whiff": desc.str.startswith("swinging_strike").fillna(False).astype("int8"),
        "called_strike": (desc == CALLED_STRIKE_DESCRIPTION).astype("int8"),
    })
    # None-out NaN so the JSON payload carries null, not the string "nan".
    return out.astype(object).where(out.notna(), None).to_dict(orient="records")


# Slicer option constants — UI choices map to these values.
LOCATION_OPTIONS = (None, "in", "out")
PLATOON_OPTIONS = (None, "same", "opp")
P_THROWS_OPTIONS = (None, "L", "R")


def compute(
    pitch_types=None,       # None -> all offspeed pitch_types
    location=None,          # None / "in" / "out"
    platoon=None,           # None / "same" / "opp"
    p_throws_filter=None,   # None / "L" / "R"
    velo_floor=90.9,        # None -> no velo floor
    min_fastballs=50,       # 0/None -> no minimum
    min_4seam=30,
    min_offspeed=30,
    min_swings=0,           # filtered swing count gate
    min_pitches=0,          # filtered pitch count gate
    divisions=None,
):
    """
    Returns the data dict the UI renders.

    `pitch_types`, `location`, `platoon`, `p_throws_filter` are pitch-level
    *slicers*: they restrict which first-pitch offspeed pitches contribute to
    the headline stats, breakdowns, and per-pitch table. They do NOT change
    which pitchers are eligible — that's controlled by the
    pitcher-level gates (`velo_floor`, `min_fastballs`, `min_4seam`,
    `min_offspeed`).

    `min_swings` / `min_pitches` are sample-size gates on the *filtered*
    counts: a pitcher needs at least that many qualifying swings/pitches
    *under the active slicer* to be included.
    """
    df = load_pitches(divisions=divisions)

    min_fastballs = int(min_fastballs or 0)
    min_4seam = int(min_4seam or 0)
    min_offspeed = int(min_offspeed or 0)
    min_swings = int(min_swings or 0)
    min_pitches = int(min_pitches or 0)

    # 1) Per-pitcher metrics (always on FULL data — these are the X-vars and
    # the eligibility inputs; they shouldn't move when a slicer changes).
    fb = df[df["pitch_type"].isin(FASTBALL_TYPES)]
    fb_grouped = fb.groupby("pitcher")["release_speed"]
    avg_fb_velo = fb_grouped.mean()
    fb_count = fb_grouped.size()

    # Primary fastball per pitcher: whichever of FF / SI they throw more of.
    # Movement + release traits are computed on *that* pitch only, since a
    # sinker and a 4-seam have structurally different shapes and averaging
    # them together would be nonsense for mixed-arsenal guys.
    ff_ct = df[df["pitch_type"] == "FF"].groupby("pitcher").size()
    si_ct = df[df["pitch_type"] == "SI"].groupby("pitcher").size()
    fb_kind_counts = pd.DataFrame({"FF": ff_ct, "SI": si_ct}).fillna(0)
    primary_fb_kind = fb_kind_counts.idxmax(axis=1).where(
        fb_kind_counts.sum(axis=1) > 0
    )
    pfb_mask = df["pitch_type"] == df["pitcher"].map(primary_fb_kind)
    pfb = df[pfb_mask]
    pfb_grouped = pfb.groupby("pitcher")
    avg_pfb_ivb = pfb_grouped["pfx_z"].mean() * 12
    avg_pfb_hbreak_signed = pfb_grouped["pfx_x"].mean() * 12
    avg_pfb_spin = pfb_grouped["release_spin_rate"].mean()
    avg_pfb_extension = pfb_grouped["release_extension"].mean()
    avg_pfb_rel_x = pfb_grouped["release_pos_x"].mean()
    avg_pfb_rel_z = pfb_grouped["release_pos_z"].mean()

    is_offspeed_pitch = df["pitch_type"].isin(OFFSPEED_PITCH_TYPES)
    os_grouped = df[is_offspeed_pitch].groupby("pitcher")
    avg_os_ivb = os_grouped["pfx_z"].mean() * 12
    avg_os_hbreak_signed = os_grouped["pfx_x"].mean() * 12
    avg_os_velo = os_grouped["release_speed"].mean()
    avg_os_rel_x = os_grouped["release_pos_x"].mean()
    avg_os_rel_z = os_grouped["release_pos_z"].mean()
    os_count = os_grouped.size()

    avg_vsep = (avg_pfb_ivb - avg_os_ivb).dropna()
    avg_hsep = (avg_pfb_hbreak_signed - avg_os_hbreak_signed).abs().dropna()
    avg_delta_v = (avg_fb_velo - avg_os_velo).dropna()
    avg_release_sep = (
        ((avg_pfb_rel_x - avg_os_rel_x) ** 2
         + (avg_pfb_rel_z - avg_os_rel_z) ** 2) ** 0.5 * 12
    ).dropna()

    total_pitches_pp = df.groupby("pitcher").size()
    fb_usage_pct = (fb_count / total_pitches_pp * 100).dropna()

    # Most-common team per pitcher (handles mid-season trades gracefully).
    if "pitching_team" in df.columns:
        team_map = (
            df.dropna(subset=["pitching_team"])
              .groupby("pitcher")["pitching_team"]
              .agg(lambda s: s.mode().iat[0] if not s.mode().empty else None)
              .to_dict()
        )
    else:
        team_map = {}

    # 2) Pitcher eligibility (full-data based). Slicers don't move this set.
    elig_mask = fb_count >= min_fastballs
    if velo_floor is not None:
        elig_mask = elig_mask & (avg_fb_velo >= velo_floor)
        excluded_below_floor = avg_fb_velo[
            (fb_count >= min_fastballs) & (avg_fb_velo < velo_floor)
        ]
    else:
        excluded_below_floor = pd.Series(dtype=float)
    eligible_ids_full = set(avg_fb_velo[elig_mask].index)

    name_col = "pitcher_name" if "pitcher_name" in df.columns else "player_name"
    first_seen = df.drop_duplicates("pitcher").set_index("pitcher")
    name_map = first_seen[name_col].to_dict()
    division_map = first_seen["division"].to_dict() if "division" in df.columns else {}

    # 3) First-pitch offspeed slice (pre-slicer), augmented with the
    # slicer dimension columns once so we can filter cheaply.
    is_first = df["pitch_number"] == 1
    fo_all = df[is_first & is_offspeed_pitch & df["pitcher"].isin(eligible_ids_full)].copy()
    fo_all["in_zone"] = (fo_all["zone"] <= 9).astype("Int64")
    fo_all["same_hand"] = (fo_all["p_throws"] == fo_all["stand"]).astype("Int64")

    # 4) Apply pitch-level slicers
    fo = fo_all
    if pitch_types:
        fo = fo[fo["pitch_type"].isin(pitch_types)]
    if location == "in":
        fo = fo[fo["in_zone"] == 1]
    elif location == "out":
        fo = fo[fo["in_zone"] == 0]
    if platoon == "same":
        fo = fo[fo["same_hand"] == 1]
    elif platoon == "opp":
        fo = fo[fo["same_hand"] == 0]
    if p_throws_filter in ("L", "R"):
        fo = fo[fo["p_throws"] == p_throws_filter]

    # 5) Per-pitcher swing/whiff counts on FILTERED data
    fo_swings_df = fo[fo["description"].isin(SWING_DESCRIPTIONS)]
    fo_whiffs_df = fo_swings_df[fo_swings_df["description"].str.startswith("swinging_strike")]
    fo_called_df = fo[fo["description"] == CALLED_STRIKE_DESCRIPTION]
    pitches_pp = fo.groupby("pitcher").size()
    swings_pp = fo_swings_df.groupby("pitcher").size()
    whiffs_pp = fo_whiffs_df.groupby("pitcher").size()
    called_pp = fo_called_df.groupby("pitcher").size()

    # 6) Sample-size gate on filtered counts
    eligible_ids = set(eligible_ids_full)
    if min_swings > 0:
        eligible_ids &= set(swings_pp[swings_pp >= min_swings].index)
    if min_pitches > 0:
        eligible_ids &= set(pitches_pp[pitches_pp >= min_pitches].index)

    # 7) Per-pitcher rows (filtered cohort) — sorted by velo desc.
    # Only include pitchers who actually have at least one pitch under the
    # slicer; otherwise the scatter / roster fills up with empty rows.
    per_pitcher = []
    contributing_ids = sorted(
        (pid for pid in eligible_ids if pitches_pp.get(pid, 0) > 0),
        key=lambda p: -avg_fb_velo[p],
    )
    def _get(series, pid):
        return float(series[pid]) if pid in series.index and pd.notna(series[pid]) else None

    for pid in contributing_ids:
        sw = int(swings_pp.get(pid, 0))
        wh = int(whiffs_pp.get(pid, 0))
        cs = int(called_pp.get(pid, 0))
        pc = int(pitches_pp.get(pid, 0))
        per_pitcher.append({
            "id": int(pid),
            "name": name_map.get(pid, str(pid)),
            "division": division_map.get(pid),
            "team": team_map.get(pid),
            "velo": float(avg_fb_velo[pid]),
            "ivb": _get(avg_pfb_ivb, pid),
            "os_ivb": _get(avg_os_ivb, pid),
            "vsep": _get(avg_vsep, pid),
            "fo_pitches": pc,
            "fo_swings": sw,
            "fo_whiffs": wh,
            "fo_called": cs,
            "whiff_rate": round(wh / sw * 100, 1) if sw else None,
            "csw_rate": round((wh + cs) / pc * 100, 1) if pc else None,
        })

    # Per-pitcher trait table — all FB traits + tunneling/deception
    # separations + first-pitch OS whiff%. Unlike `per_pitcher`, this is keyed
    # to the *full* eligible roster (not gated by the filtered slicer) so the
    # team filter acts on a stable pitcher universe.
    pitcher_traits = []
    for pid in sorted(eligible_ids_full, key=lambda p: name_map.get(p, str(p))):
        sw = int(swings_pp.get(pid, 0))
        wh = int(whiffs_pp.get(pid, 0))
        pfb_hbreak = _get(avg_pfb_hbreak_signed, pid)
        fb_kind = primary_fb_kind.get(pid)
        pitcher_traits.append({
            "id": int(pid),
            "name": name_map.get(pid, str(pid)),
            "team": team_map.get(pid),
            "division": division_map.get(pid),
            "fb_kind": fb_kind if isinstance(fb_kind, str) else None,
            "fb_velo": float(avg_fb_velo[pid]),
            "fb_ivb": _get(avg_pfb_ivb, pid),
            "fb_hbreak": abs(pfb_hbreak) if pfb_hbreak is not None else None,
            "fb_spin": _get(avg_pfb_spin, pid),
            "fb_extension": _get(avg_pfb_extension, pid),
            "fb_usage_pct": _get(fb_usage_pct, pid),
            "delta_v": _get(avg_delta_v, pid),
            "vsep": _get(avg_vsep, pid),
            "hsep": _get(avg_hsep, pid),
            "release_sep": _get(avg_release_sep, pid),
            "fo_swings": sw,
            "whiff_rate": round(wh / sw * 100, 1) if sw else None,
        })

    # 8) Headline summary on the filtered + eligible cohort. Counts the
    # pitchers actually contributing under this slicer, not the full
    # eligible roster.
    fo_eligible = fo[fo["pitcher"].isin(eligible_ids)]
    summary = _pitch_stats(fo_eligible)
    summary["n_pitchers"] = int(fo_eligible["pitcher"].nunique()) if not fo_eligible.empty else 0
    summary["n_eligible_total"] = len(eligible_ids)

    # 9) Breakdowns — same metric across each slicer dimension within the
    # filtered cohort. Lets the user compare across families / zone / platoon
    # without losing the active filter context.
    def _split(group_col, levels):
        rows = []
        for label, mask in levels:
            sub = fo_eligible[mask]
            if sub.empty:
                stats = _pitch_stats(sub)
                n_pitchers = 0
            else:
                stats = _pitch_stats(sub)
                n_pitchers = sub["pitcher"].nunique()
            rows.append({"label": label, "stats": stats, "n_pitchers": n_pitchers})
        return rows

    pt_levels = []
    if not fo_eligible.empty:
        present_types = (
            fo_eligible["pitch_type"].dropna().value_counts().index.tolist()
        )
        for pt in present_types:
            label = f"{PITCH_TYPE_LABELS.get(pt, pt)} ({pt})"
            pt_levels.append((label, fo_eligible["pitch_type"] == pt))

    breakdowns = {
        "by_pitch_type": _split("pitch_type", pt_levels),
        "by_zone": _split("in_zone", [
            ("In zone",     fo_eligible["in_zone"] == 1),
            ("Out of zone", fo_eligible["in_zone"] == 0),
        ]),
        "by_platoon": _split("same_hand", [
            ("Same hand", fo_eligible["same_hand"] == 1),
            ("Opp hand",  fo_eligible["same_hand"] == 0),
        ]),
    }

    # 10) Per-pitch detail (filtered + eligible) with velo/vsep columns
    velo_dict = avg_fb_velo.to_dict()
    vsep_dict = avg_vsep.to_dict()
    pitch_details = _build_pitch_details(
        fo_eligible, name_map, team_map, velo_dict, vsep_dict
    )

    excluded = [
        {"id": int(pid), "name": name_map.get(pid, str(pid)), "velo": float(velo)}
        for pid, velo in excluded_below_floor.sort_values().items()
    ]
    divisions_loaded = sorted(df["division"].dropna().unique().tolist()) if "division" in df.columns else []

    return {
        "params": {
            "pitch_types": sorted(pitch_types) if pitch_types else None,
            "location": location,
            "platoon": platoon,
            "p_throws_filter": p_throws_filter,
            "velo_floor": velo_floor,
            "min_fastballs": min_fastballs,
            "min_4seam": min_4seam,
            "min_offspeed": min_offspeed,
            "min_swings": min_swings,
            "min_pitches": min_pitches,
            "divisions": divisions_loaded,
        },
        "summary": summary,
        "per_pitcher": per_pitcher,
        "pitcher_traits": pitcher_traits,
        "breakdowns": breakdowns,
        "pitch_details": pitch_details,
        "excluded_below_floor": excluded,
    }


def print_summary(divisions=None):
    """Lightweight CLI sanity check — prints the headline stats on full
    (unfiltered) data so you can spot-check `compute()` from a terminal."""
    r = compute(divisions=divisions)
    p = r["params"]
    s = r["summary"]
    print("=== First-Pitch Offspeed Whiff Rate (unfiltered) ===")
    print(f"Divisions loaded: {p['divisions'] or '(none tagged)'}")
    print(f"Velo floor: {p['velo_floor']} mph | min fastballs: {p['min_fastballs']}")
    print()
    print(f"Pitchers (eligible): {s['n_pitchers']}")
    print(f"First-pitch offspeed pitches: {s['pitches']:,}")
    print(f"  swings: {s['swings']:,}  whiffs: {s['whiffs']:,}  called: {s['called_strikes']:,}")
    print(f"  whiff%: {s['whiff_rate']}    CSW%: {s['csw_rate']}")
    print()
    print("=== Breakdowns ===")
    for key, label in (("by_pitch_type", "Pitch type"),
                       ("by_zone",       "Location"),
                       ("by_platoon",    "Platoon")):
        print(f"-- {label} --")
        for row in r["breakdowns"][key]:
            st = row["stats"]
            wr = f"{st['whiff_rate']}%" if st["swings"] else "n/a"
            csw = f"{st['csw_rate']}%" if st["pitches"] else "n/a"
            print(f"  {row['label']:11s}  pitches={st['pitches']:5d}  swings={st['swings']:5d}  "
                  f"whiff%={wr:>6s}  CSW%={csw:>6s}")
        print()
    return r


if __name__ == "__main__":
    import sys
    cli_divs = sys.argv[1:] if len(sys.argv) > 1 else None
    print_summary(divisions=cli_divs)
