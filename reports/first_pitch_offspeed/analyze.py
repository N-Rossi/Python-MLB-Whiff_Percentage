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
import statsmodels.api as sm

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


def load_pitches(divisions=None):
    """
    Load and concat every {division}_starters_*_pitches.parquet in the data
    dir. If `divisions` is given, restrict to those. Adds/repairs the
    `division` column from the filename for older files that predate it.
    """
    paths = sorted(DATA_DIR.glob(PITCHES_GLOB))
    if not paths:
        raise FileNotFoundError(
            f"No pitch parquet files found in {DATA_DIR}. "
            f"Run `python fetch_starters.py <division>` first."
        )

    frames = []
    for path in paths:
        m = _DIVISION_FROM_FILENAME.match(path.name)
        div = m.group(1) if m else path.stem
        if divisions and div not in divisions:
            continue
        df = pd.read_parquet(path)
        if "division" not in df.columns:
            df["division"] = div
        frames.append(df)

    if not frames:
        raise FileNotFoundError(
            f"No pitch parquet files matched divisions={divisions}. "
            f"Available: {available_divisions()}"
        )
    return pd.concat(frames, ignore_index=True)


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


def _fit_weighted_or_ols(y, X, weights=None):
    """WLS when valid positive weights are provided, else plain OLS."""
    if weights is not None:
        w = pd.Series(weights).fillna(0).to_numpy()
        if (w > 0).any():
            return sm.WLS(y, X, weights=w).fit(), "WLS (weighted by swings)"
    return sm.OLS(y, X).fit(), "OLS (unweighted)"


def _run_regression(per_pitcher_df):
    """
    Bivariate WLS: Y = per-pitcher first-pitch offspeed whiff%,
    X = vsep (in). Each pitcher weighted by their first-pitch OS swing
    count, so high-sample pitchers get more pull and low-sample pitchers
    don't drag the slope around with noisy whiff%.
    """
    df = per_pitcher_df.dropna(subset=["whiff_rate", "vsep"]).copy()
    n = len(df)
    if n < 4:
        return {
            "n": n,
            "skipped_reason": (
                f"Need >= 4 pitchers with a defined whiff% and VSep to fit "
                f"the regression (have {n}). Loosen sample-size gates or add "
                f"more divisions."
            ),
        }

    X = sm.add_constant(df[["vsep"]])
    y = df["whiff_rate"]
    weights = df["swings"] if "swings" in df.columns else None
    model, fit_method = _fit_weighted_or_ols(y, X, weights=weights)

    ci = model.conf_int()
    pretty = {
        "const": "Intercept (vsep = 0)",
        "vsep": "VSep (in) — variable of interest",
    }
    coefficients = [
        {
            "name": name,
            "label": pretty[name],
            "coef": float(model.params[name]),
            "std_err": float(model.bse[name]),
            "t": float(model.tvalues[name]),
            "p_value": float(model.pvalues[name]),
            "ci_lower": float(ci.loc[name, 0]),
            "ci_upper": float(ci.loc[name, 1]),
        }
        for name in ["const", "vsep"]
    ]

    return {
        "n": n,
        "fit_method": fit_method,
        "total_weight": float(weights.sum()) if weights is not None else None,
        "r_squared": float(model.rsquared),
        "adj_r_squared": float(model.rsquared_adj),
        "f_statistic": float(model.fvalue) if model.fvalue is not None else None,
        "f_p_value": float(model.f_pvalue) if model.f_pvalue is not None else None,
        "coefficients": coefficients,
    }


def _run_regression_with_high_velo(per_pitcher_df, velo_cut=95.0):
    """
    WLS: Y = per-pitcher first-pitch offspeed whiff%,
    X = vsep (continuous, in) + high_velo (1 if avg FB >= velo_cut mph).
    Adds high_velo as a control on top of the bivariate vsep model.
    """
    df = per_pitcher_df.dropna(subset=["whiff_rate", "vsep", "velo"]).copy()
    n = len(df)
    if n < 4:
        return {
            "n": n,
            "skipped_reason": (
                f"Need >= 4 pitchers with a defined whiff%, VSep, and velo "
                f"to fit the regression (have {n})."
            ),
            "velo_cut": velo_cut,
        }

    df["high_velo"] = (df["velo"] >= velo_cut).astype(int)

    X = sm.add_constant(df[["vsep", "high_velo"]])
    y = df["whiff_rate"]
    weights = df["swings"] if "swings" in df.columns else None
    model, fit_method = _fit_weighted_or_ols(y, X, weights=weights)

    ci = model.conf_int()
    pretty = {
        "const": "Intercept (low velo, vsep = 0)",
        "vsep": "VSep (in) — variable of interest",
        "high_velo": f"High velo (FB >= {velo_cut} mph)",
    }
    coefficients = [
        {
            "name": name,
            "label": pretty[name],
            "coef": float(model.params[name]),
            "std_err": float(model.bse[name]),
            "t": float(model.tvalues[name]),
            "p_value": float(model.pvalues[name]),
            "ci_lower": float(ci.loc[name, 0]),
            "ci_upper": float(ci.loc[name, 1]),
        }
        for name in ["const", "vsep", "high_velo"]
    ]

    return {
        "n": n,
        "velo_cut": velo_cut,
        "fit_method": fit_method,
        "total_weight": float(weights.sum()) if weights is not None else None,
        "r_squared": float(model.rsquared),
        "adj_r_squared": float(model.rsquared_adj),
        "f_statistic": float(model.fvalue) if model.fvalue is not None else None,
        "f_p_value": float(model.f_pvalue) if model.f_pvalue is not None else None,
        "coefficients": coefficients,
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


def _build_pitch_details(d, name_map, division_map, velo_dict, vsep_dict):
    """
    One row per first-pitch offspeed pitch (already filtered by the caller).
    Assumes `d` already has `in_zone` and `same_hand` cols. Adds the pitcher's
    avg FB velo and VSep so each row carries the X-vars from the regression
    alongside the pitch-level slicer columns.
    """
    if d.empty:
        return []

    d = d.copy()
    d["swing"] = d["description"].isin(SWING_DESCRIPTIONS).astype(int)
    d["whiff"] = d["description"].str.startswith("swinging_strike").astype(int)
    d["called_strike"] = (d["description"] == CALLED_STRIKE_DESCRIPTION).astype(int)

    sort_cols = [c for c in ("pitcher", "game_date", "at_bat_number") if c in d.columns]
    if sort_cols:
        d = d.sort_values(sort_cols)

    rows = []
    for r in d.itertuples(index=False):
        rd = r._asdict()
        pid = rd["pitcher"]
        rows.append({
            "pitcher_id": int(pid),
            "pitcher": name_map.get(pid, str(pid)),
            "division": division_map.get(pid),
            "game_date": str(rd.get("game_date")) if rd.get("game_date") is not None else None,
            "velo": float(velo_dict[pid]) if pid in velo_dict else None,
            "vsep": float(vsep_dict[pid]) if pid in vsep_dict else None,
            "pitch_type": rd.get("pitch_type"),
            "p_throws": rd.get("p_throws"),
            "stand": rd.get("stand"),
            "in_zone": int(rd["in_zone"]) if pd.notna(rd["in_zone"]) else None,
            "same_hand": int(rd["same_hand"]) if pd.notna(rd["same_hand"]) else None,
            "description": rd.get("description"),
            "swing": int(rd["swing"]),
            "whiff": int(rd["whiff"]),
            "called_strike": int(rd["called_strike"]),
        })
    return rows


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
    the headline stats, breakdowns, regressions, and per-pitch table. They do
    NOT change which pitchers are eligible — that's controlled by the
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

    ff = df[df["pitch_type"] == "FF"]
    ff_grouped = ff.groupby("pitcher")["pfx_z"]
    avg_ff_ivb = ff_grouped.mean() * 12
    ff_count = ff_grouped.size()

    is_offspeed_pitch = df["pitch_type"].isin(OFFSPEED_PITCH_TYPES)
    os_grouped = df[is_offspeed_pitch].groupby("pitcher")["pfx_z"]
    avg_os_ivb = os_grouped.mean() * 12
    os_count = os_grouped.size()

    avg_vsep = (avg_ff_ivb - avg_os_ivb).dropna()

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
    for pid in contributing_ids:
        sw = int(swings_pp.get(pid, 0))
        wh = int(whiffs_pp.get(pid, 0))
        cs = int(called_pp.get(pid, 0))
        pc = int(pitches_pp.get(pid, 0))
        per_pitcher.append({
            "id": int(pid),
            "name": name_map.get(pid, str(pid)),
            "division": division_map.get(pid),
            "velo": float(avg_fb_velo[pid]),
            "ivb": float(avg_ff_ivb[pid]) if pid in avg_ff_ivb.index else None,
            "os_ivb": float(avg_os_ivb[pid]) if pid in avg_os_ivb.index else None,
            "vsep": float(avg_vsep[pid]) if pid in avg_vsep.index else None,
            "fo_pitches": pc,
            "fo_swings": sw,
            "fo_whiffs": wh,
            "fo_called": cs,
            "whiff_rate": round(wh / sw * 100, 1) if sw else None,
            "csw_rate": round((wh + cs) / pc * 100, 1) if pc else None,
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
        fo_eligible, name_map, division_map, velo_dict, vsep_dict
    )

    # 11) Regressions (WLS) on filtered per-pitcher data
    per_pitcher_df = pd.DataFrame([
        {
            "id": p["id"],
            "velo": p["velo"],
            "vsep": p["vsep"] if p["vsep"] is not None else np.nan,
            "whiff_rate": (p["fo_whiffs"] / p["fo_swings"] * 100) if p["fo_swings"] else np.nan,
            "swings": p["fo_swings"],
        }
        for p in per_pitcher
    ])
    regression = _run_regression(per_pitcher_df)
    regression_velo = _run_regression_with_high_velo(per_pitcher_df, velo_cut=95.0)

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
        "breakdowns": breakdowns,
        "pitch_details": pitch_details,
        "regression": regression,
        "regression_velo": regression_velo,
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
    print("=== Regressions ===")
    for tag, reg in (("vsep only", r["regression"]),
                     ("vsep + high_velo", r["regression_velo"])):
        if reg.get("skipped_reason"):
            print(f"{tag}: SKIPPED — {reg['skipped_reason']}")
            continue
        print(f"{tag}: n={reg['n']} R²={reg['r_squared']:.3f} ({reg.get('fit_method')})")
        for c in reg["coefficients"]:
            print(f"  {c['name']:>10s}  beta={c['coef']:+.3f}  se={c['std_err']:.3f}  p={c['p_value']:.4f}")
    return r


if __name__ == "__main__":
    import sys
    cli_divs = sys.argv[1:] if len(sys.argv) > 1 else None
    print_summary(divisions=cli_divs)
