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
PITCHES_GLOB = "*_starters_*_pitches.csv"

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


_DIVISION_FROM_FILENAME = re.compile(r"^(.+?)_starters_\d+_pitches\.csv$")


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
    Load and concat every {division}_starters_*_pitches.csv in the data dir.
    If `divisions` is given, restrict to those. Adds/repairs the `division`
    column from the filename for older CSVs that predate that column.
    """
    paths = sorted(DATA_DIR.glob(PITCHES_GLOB))
    if not paths:
        raise FileNotFoundError(
            f"No pitch CSVs found in {DATA_DIR}. "
            f"Run `python fetch_starters.py <division>` first."
        )

    frames = []
    for path in paths:
        m = _DIVISION_FROM_FILENAME.match(path.name)
        div = m.group(1) if m else path.stem
        if divisions and div not in divisions:
            continue
        df = pd.read_csv(path)
        if "division" not in df.columns:
            df["division"] = div
        frames.append(df)

    if not frames:
        raise FileNotFoundError(
            f"No pitch CSVs matched divisions={divisions}. "
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


def _run_regression(per_pitcher_df, velo_cut, vsep_cut):
    """
    OLS of per-pitcher first-pitch offspeed whiff% on:
        intercept, high_velo, wide_vsep, high_velo * wide_vsep

    Pitchers without a defined whiff_rate or vsep are dropped (no swings,
    or insufficient FF / offspeed pitches to compute vsep). Returns a dict
    with the coefficient table, fit statistics, the 2x2 cell means used
    for plain-English interpretation, and the eligible N.
    """
    df = per_pitcher_df.dropna(subset=["whiff_rate", "vsep", "velo"]).copy()
    n = len(df)
    if n < 4:
        return {
            "n": n,
            "skipped_reason": (
                f"Need >= 4 pitchers with a defined whiff% and VSep to fit "
                f"the regression (have {n}). Loosen sample-size gates or add "
                f"more divisions."
            ),
            "velo_cut": velo_cut,
            "vsep_cut": vsep_cut,
        }

    df["high_velo"] = (df["velo"] >= velo_cut).astype(int)
    df["wide_vsep"] = (df["vsep"] >= vsep_cut).astype(int)
    df["interaction"] = df["high_velo"] * df["wide_vsep"]

    X = sm.add_constant(df[["high_velo", "wide_vsep", "interaction"]])
    y = df["whiff_rate"]
    model = sm.OLS(y, X).fit()

    ci = model.conf_int()
    pretty = {
        "const": "Intercept (low velo, narrow vsep)",
        "high_velo": f"High velo (FB >= {velo_cut} mph)",
        "wide_vsep": f"Wide vsep (>= {vsep_cut}\")",
        "interaction": "High velo × Wide vsep",
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
        for name in ["const", "high_velo", "wide_vsep", "interaction"]
    ]

    # 2x2 cell means: rows = velo, cols = vsep
    cells = []
    for hv in (0, 1):
        for wv in (0, 1):
            cell = df[(df["high_velo"] == hv) & (df["wide_vsep"] == wv)]
            cells.append({
                "high_velo": bool(hv),
                "wide_vsep": bool(wv),
                "n": len(cell),
                "mean_whiff_rate": float(cell["whiff_rate"].mean()) if len(cell) else None,
            })

    return {
        "n": n,
        "velo_cut": velo_cut,
        "vsep_cut": vsep_cut,
        "r_squared": float(model.rsquared),
        "adj_r_squared": float(model.rsquared_adj),
        "f_statistic": float(model.fvalue) if model.fvalue is not None else None,
        "f_p_value": float(model.f_pvalue) if model.f_pvalue is not None else None,
        "coefficients": coefficients,
        "cells": cells,
    }


def compute_buckets(
    velo_threshold=94.9,   # None -> skip high/low velo split
    velo_floor=90.9,       # None -> no velo floor (include everyone)
    vsep_threshold=18.0,   # None -> skip vertical-separation sub-split
    min_fastballs=50,      # 0/None -> no minimum
    min_4seam=30,
    min_offspeed=30,
    min_swings=0,          # 0/None -> no minimum first-pitch offspeed swings
    min_pitches=0,         # 0/None -> no minimum first-pitch offspeed pitches (CSW% sample gate)
    regression_velo_cut=None,  # None -> falls back to velo_threshold (or 95.0 if that is also off)
    regression_vsep_cut=16.0,  # IVB-separation cutoff used by the regression dummy
    divisions=None,
):
    """
    Pure-data version: returns a structured dict the CLI and UI can render.
    Every threshold parameter accepts None to disable that filter/split.

    `divisions` is an optional iterable of division keys; if None, every
    cached division is included.
    """
    df = load_pitches(divisions=divisions)

    # Coerce min_* to ints — None means 0
    min_fastballs = int(min_fastballs or 0)
    min_4seam = int(min_4seam or 0)
    min_offspeed = int(min_offspeed or 0)
    min_swings = int(min_swings or 0)
    min_pitches = int(min_pitches or 0)

    # 1) Per-pitcher metrics
    fb = df[df["pitch_type"].isin(FASTBALL_TYPES)]
    fb_grouped = fb.groupby("pitcher")["release_speed"]
    avg_fb_velo = fb_grouped.mean()
    fb_count = fb_grouped.size()

    ff = df[df["pitch_type"] == "FF"]
    ff_grouped = ff.groupby("pitcher")["pfx_z"]
    avg_ff_ivb = ff_grouped.mean() * 12
    ff_count = ff_grouped.size()

    # Per-pitcher offspeed IVB (over every non-fastball/cutter pitch).
    is_offspeed_pitch = ~df["pitch_type"].isin(NON_OFFSPEED) & df["pitch_type"].notna()
    os_pitches_df = df[is_offspeed_pitch]
    os_grouped = os_pitches_df.groupby("pitcher")["pfx_z"]
    avg_os_ivb = os_grouped.mean() * 12
    os_count = os_grouped.size()

    # Per-pitcher vertical separation = 4-seam IVB - offspeed IVB (inches).
    # Positive (typical) means the fastball rises more than the offspeed —
    # bigger values = more vertical contrast between the two pitch families.
    avg_vsep = (avg_ff_ivb - avg_os_ivb).dropna()

    # 2) First-pitch offspeed slice & per-pitcher swing/whiff counts
    # (computed before eligibility so we can gate on min_swings)
    is_first = df["pitch_number"] == 1
    first_offspeed = df[is_first & is_offspeed_pitch]
    fo_swings = first_offspeed[first_offspeed["description"].isin(SWING_DESCRIPTIONS)]
    fo_whiffs = fo_swings[fo_swings["description"].str.startswith("swinging_strike")]
    fo_called = first_offspeed[first_offspeed["description"] == CALLED_STRIKE_DESCRIPTION]
    pitches_pp = first_offspeed.groupby("pitcher").size()
    swings_pp = fo_swings.groupby("pitcher").size()
    whiffs_pp = fo_whiffs.groupby("pitcher").size()
    called_pp = fo_called.groupby("pitcher").size()

    # 3) Eligibility
    elig_mask = fb_count >= min_fastballs
    if velo_floor is not None:
        elig_mask = elig_mask & (avg_fb_velo >= velo_floor)
        excluded_below_floor = avg_fb_velo[(fb_count >= min_fastballs) & (avg_fb_velo < velo_floor)]
    else:
        excluded_below_floor = pd.Series(dtype=float)
    if min_swings > 0:
        # Reindex swings_pp to align with avg_fb_velo so missing pitchers count as 0 swings
        swings_aligned = swings_pp.reindex(avg_fb_velo.index, fill_value=0)
        elig_mask = elig_mask & (swings_aligned >= min_swings)
    if min_pitches > 0:
        pitches_aligned = pitches_pp.reindex(avg_fb_velo.index, fill_value=0)
        elig_mask = elig_mask & (pitches_aligned >= min_pitches)
    eligible = avg_fb_velo[elig_mask]
    eligible_ids = set(eligible.index)

    name_col = "pitcher_name" if "pitcher_name" in df.columns else "player_name"
    first_seen = df.drop_duplicates("pitcher").set_index("pitcher")
    name_map = first_seen[name_col].to_dict()
    division_map = first_seen["division"].to_dict() if "division" in df.columns else {}

    def _roster(ids):
        rows = []
        for pid in sorted(ids, key=lambda p: -avg_fb_velo[p]):
            sw = int(swings_pp.get(pid, 0))
            wh = int(whiffs_pp.get(pid, 0))
            cs = int(called_pp.get(pid, 0))
            pc = int(pitches_pp.get(pid, 0))
            rows.append({
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
        return rows

    def _make_bucket(label, ids):
        return {
            "label": label,
            "stats": _pitch_stats(first_offspeed[first_offspeed["pitcher"].isin(ids)]),
            "roster": _roster(ids),
        }

    # 4) Build comparisons dynamically based on which thresholds are enabled
    comparisons = []

    # Velo split (or single "All" bucket if velo threshold is off)
    if velo_threshold is not None:
        high_ids = set(eligible[eligible >= velo_threshold].index)
        low_ids = set(eligible[eligible < velo_threshold].index)
        comparisons.append({
            "title": "Hard throwers vs. soft throwers",
            "delta_label": "Δ (high − low)",
            "buckets": [
                _make_bucket(f"High-velo (>= {velo_threshold} mph)", high_ids),
                _make_bucket(f"Low-velo  (<  {velo_threshold} mph)", low_ids),
            ],
        })
        sub_split_ids = high_ids
        sub_split_context = "Within hard throwers"
    else:
        comparisons.append({
            "title": "All eligible pitchers",
            "delta_label": None,
            "buckets": [_make_bucket("All eligible", eligible_ids)],
        })
        sub_split_ids = eligible_ids
        sub_split_context = "All eligible pitchers"

    # Vertical separation sub-split (FF IVB - OS IVB).
    # Needs both enough 4-seamers AND enough offspeed pitches to compute.
    if vsep_threshold is not None:
        with_vsep = {
            pid for pid in sub_split_ids
            if ff_count.get(pid, 0) >= min_4seam
            and os_count.get(pid, 0) >= min_offspeed
            and pid in avg_vsep.index
        }
        no_vsep = sub_split_ids - with_vsep
        wide = {pid for pid in with_vsep if avg_vsep[pid] >= vsep_threshold}
        narrow = with_vsep - wide
        cmp = {
            "title": f"{sub_split_context}: wide vs. narrow vertical separation",
            "delta_label": "Δ (wide − narrow)",
            "buckets": [
                _make_bucket(f"VSep >= {vsep_threshold}\"", wide),
                _make_bucket(f"VSep <  {vsep_threshold}\"", narrow),
            ],
        }
        if no_vsep:
            cmp["excluded_note"] = (
                f"{len(no_vsep)} pitcher(s) excluded from vertical-separation split "
                f"(fewer than {min_4seam} 4-seamers or {min_offspeed} offspeed pitches)"
            )
            cmp["excluded_roster"] = _roster(no_vsep)
        comparisons.append(cmp)

    excluded = [
        {"id": int(pid), "name": name_map.get(pid, str(pid)), "velo": float(velo)}
        for pid, velo in excluded_below_floor.sort_values().items()
    ]

    divisions_loaded = sorted(df["division"].dropna().unique().tolist()) if "division" in df.columns else []

    # 5) Per-pitcher table for the regression — built from the same eligible
    # set as the bucket comparisons, so the regression and the headline
    # numbers stay consistent with the active sidebar filters.
    reg_rows = []
    for pid in eligible_ids:
        sw = int(swings_pp.get(pid, 0))
        wh = int(whiffs_pp.get(pid, 0))
        reg_rows.append({
            "id": int(pid),
            "velo": float(avg_fb_velo[pid]),
            "vsep": float(avg_vsep[pid]) if pid in avg_vsep.index else np.nan,
            "whiff_rate": (wh / sw * 100) if sw else np.nan,
        })
    per_pitcher_df = pd.DataFrame(reg_rows)

    eff_velo_cut = (
        regression_velo_cut
        if regression_velo_cut is not None
        else (velo_threshold if velo_threshold is not None else 95.0)
    )
    regression = _run_regression(per_pitcher_df, eff_velo_cut, regression_vsep_cut)

    return {
        "params": {
            "velo_threshold": velo_threshold,
            "velo_floor": velo_floor,
            "vsep_threshold": vsep_threshold,
            "min_fastballs": min_fastballs,
            "min_4seam": min_4seam,
            "min_offspeed": min_offspeed,
            "min_swings": min_swings,
            "min_pitches": min_pitches,
            "regression_velo_cut": eff_velo_cut,
            "regression_vsep_cut": regression_vsep_cut,
            "divisions": divisions_loaded,
        },
        "comparisons": comparisons,
        "excluded_below_floor": excluded,
        "regression": regression,
    }


def whiff_rate_by_velo_bucket(
    velo_threshold=94.9,
    velo_floor=90.9,
    vsep_threshold=18.0,
    min_fastballs=50,
    min_4seam=30,
    min_offspeed=30,
    min_swings=0,
    min_pitches=0,
    divisions=None,
):
    """
    CLI report. Walks every comparison built by compute_buckets() — set any
    threshold to None to disable that filter/split.
    """
    r = compute_buckets(
        velo_threshold=velo_threshold,
        velo_floor=velo_floor,
        vsep_threshold=vsep_threshold,
        min_fastballs=min_fastballs,
        min_4seam=min_4seam,
        min_offspeed=min_offspeed,
        min_swings=min_swings,
        min_pitches=min_pitches,
        divisions=divisions,
    )
    p = r["params"]

    def _fmt(v, suffix=""):
        return f"{v}{suffix}" if v is not None else "OFF"

    print("=== First-Pitch Offspeed Whiff Rate ===")
    print(f"Divisions loaded:  {p['divisions'] or '(none tagged)'}")
    print(f"Velo threshold:    {_fmt(p['velo_threshold'], ' mph')}   "
          f"|  velo floor: {_fmt(p['velo_floor'], ' mph')}")
    print(f"VSep threshold:    {_fmt(p['vsep_threshold'], ' in')}     "
          f"(needs >= {p['min_4seam']} FF and >= {p['min_offspeed']} OS pitches)")
    print(f"Min fastballs:     {p['min_fastballs']}    |  min 1st-pitch OS swings: {p['min_swings']}    "
          f"|  min 1st-pitch OS pitches: {p['min_pitches']}")
    print(f"VSep = avg 4-seam IVB - avg offspeed IVB (positive = fastball rises more)")
    print(f"Fastball = {sorted(FASTBALL_TYPES)}, "
          f"Offspeed = anything NOT in {sorted(NON_OFFSPEED)}")
    print(f"Whiff rate = swinging strikes / total swings")
    print(f"CSW% = (called strikes + whiffs) / total pitches\n")

    if r["excluded_below_floor"]:
        print(f"Excluded {len(r['excluded_below_floor'])} pitcher(s) below velo floor:")
        for x in r["excluded_below_floor"]:
            print(f"  {x['velo']:5.1f}  {x['name']}")
        print()

    def _print_bucket(bucket):
        s = bucket["stats"]
        print(f"  {bucket['label']}: {len(bucket['roster'])} pitchers")
        print(f"    first-pitch offspeed: {s['pitches']} pitches, {s['swings']} swings, "
              f"{s['whiffs']} whiffs, {s['called_strikes']} called strikes")
        print(f"    whiff rate: {s['whiff_rate']}%" if s['swings'] else "    whiff rate: n/a (no swings)")
        print(f"    CSW%:       {s['csw_rate']}%" if s['pitches'] else "    CSW%:       n/a (no pitches)")

    def _print_roster(label, roster):
        print(f"\n  {label} ({len(roster)}):")
        for x in roster:
            ivb_str = f"  FF-IVB {x['ivb']:5.1f}\"" if x.get("ivb") is not None else ""
            os_ivb_str = f"  OS-IVB {x['os_ivb']:5.1f}\"" if x.get("os_ivb") is not None else ""
            vsep_str = f"  VSep {x['vsep']:5.1f}\"" if x.get("vsep") is not None else ""
            wr = (f"{x['whiff_rate']:5.1f}% ({x['fo_whiffs']}/{x['fo_swings']})"
                  if x.get("whiff_rate") is not None else "  n/a (0 swings)")
            csw = (f"{x['csw_rate']:5.1f}% ({x['fo_whiffs'] + x['fo_called']}/{x['fo_pitches']})"
                   if x.get("csw_rate") is not None else "  n/a (0 pitches)")
            print(f"    {x['velo']:5.1f}{ivb_str}{os_ivb_str}{vsep_str}  whiff {wr}  CSW {csw}  {x['name']}")

    for cmp in r["comparisons"]:
        print(f"=== {cmp['title']} ===")
        for bucket in cmp["buckets"]:
            _print_bucket(bucket)
        if cmp.get("excluded_note"):
            print(f"  -- {cmp['excluded_note']}")
        if len(cmp["buckets"]) == 2:
            a, b = cmp["buckets"]
            sa, sb = a["stats"], b["stats"]
            for metric_label, key, gate in (("whiff", "whiff_rate", "swings"),
                                            ("CSW", "csw_rate", "pitches")):
                if sa[gate] and sb[gate]:
                    diff = sa[key] - sb[key]
                    verdict = "HIGHER" if diff > 0 else ("LOWER" if diff < 0 else "EQUAL")
                    print(f"  >>> {metric_label}: {a['label']} is {abs(diff):.1f} pp {verdict} than {b['label']}")
        print()

    print("=== Rosters ===")
    seen_labels = set()
    for cmp in r["comparisons"]:
        for bucket in cmp["buckets"]:
            if bucket["label"] in seen_labels:
                continue
            seen_labels.add(bucket["label"])
            _print_roster(bucket["label"], bucket["roster"])
        if cmp.get("excluded_roster"):
            _print_roster(f"{cmp['title']} — excluded", cmp["excluded_roster"])

    return r


if __name__ == "__main__":
    import sys
    # Optional CLI: `python -m reports.first_pitch_offspeed.analyze nl_east al_west`
    cli_divs = sys.argv[1:] if len(sys.argv) > 1 else None
    whiff_rate_by_velo_bucket(divisions=cli_divs)
