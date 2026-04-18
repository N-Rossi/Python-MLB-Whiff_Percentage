"""
Streamlit page for the velo + IVB + CSW%/whiff-rate analysis.

Sidebar drives PITCH-LEVEL slicers (pitch family / location / platoon /
pitcher handedness / divisions). Velo and VSep are NOT slicers — they're the
project's X variables, so they appear as columns in the per-pitch table and
predictors in the regressions, not sliders that move the goalposts.
"""

import altair as alt
import pandas as pd
import streamlit as st

from reports.first_pitch_offspeed.analyze import (
    compute,
    available_divisions,
    ALL_FAMILIES,
    FASTBALL_TYPES,
    NON_OFFSPEED,
)

st.title("First-Pitch Offspeed — MLB Starters")

divs = available_divisions()
if not divs:
    st.error(
        "No pitch data found in `data/`.\n\n"
        "Run `python fetch_starters.py <division>` first to populate the cache. "
        "Use `all` to fetch every division."
    )
    st.stop()


# --- Sidebar: divisions & pitch-level slicers ---
st.sidebar.header("Divisions")
selected_divs = st.sidebar.multiselect(
    "Include data from", options=divs, default=divs,
    help="Pick which cached divisions to roll into the analysis"
)
if not selected_divs:
    st.warning("Select at least one division in the sidebar.")
    st.stop()

st.sidebar.header("Pitch-level slicers")
st.sidebar.caption(
    "Filter which **pitches** count toward the headline / breakdowns / "
    "regressions. Velo and VSep are X-variables — they show up as columns in "
    "the per-pitch table, not as slicers."
)

selected_families = st.sidebar.multiselect(
    "Pitch family",
    options=list(ALL_FAMILIES),
    default=list(ALL_FAMILIES),
    help="Slider = SL · Changeup = CH · Curveball = CU · Other = ST/KC/FS/SV/etc.",
)
if not selected_families:
    st.warning("Pick at least one pitch family in the sidebar.")
    st.stop()
all_families_selected = set(selected_families) == set(ALL_FAMILIES)

LOC_LABELS = {"All": None, "In zone (1–9)": "in", "Out of zone (11–14)": "out"}
loc_label = st.sidebar.radio(
    "Location", list(LOC_LABELS.keys()), horizontal=True,
    help="Statcast `zone` 1–9 = in the strike zone, 11–14 = outside.",
)
location = LOC_LABELS[loc_label]

PLAT_LABELS = {"All": None, "Same hand (L/L or R/R)": "same", "Opposite hand": "opp"}
plat_label = st.sidebar.radio(
    "Platoon", list(PLAT_LABELS.keys()),
    help="Same handedness = pitcher and batter both R or both L.",
)
platoon = PLAT_LABELS[plat_label]

PHAND_LABELS = {"All": None, "RHP only": "R", "LHP only": "L"}
ph_label = st.sidebar.radio(
    "Pitcher handedness", list(PHAND_LABELS.keys()), horizontal=True,
)
p_throws_filter = PHAND_LABELS[ph_label]


# --- Sidebar: plumbing (collapsed) ---
with st.sidebar.expander("Sample-size & eligibility (plumbing)", expanded=False):
    st.caption(
        "Doesn't change interpretation, just which pitchers count as a real "
        "starter and which have enough sample under the active slicer."
    )
    use_velo_floor = st.checkbox("Use velo floor", value=True, key="velo_floor_on")
    velo_floor_val = st.slider(
        "Velo floor (mph)", 85.0, 95.0, 90.9, 0.1,
        disabled=not use_velo_floor,
    )
    velo_floor = velo_floor_val if use_velo_floor else None

    min_fastballs = int(st.number_input(
        "Min fastballs (FF/SI/FT) per pitcher", 0, 500, 50, 10,
        help="Drop pitchers with fewer than this many fastballs (velo too noisy).",
    ))
    min_4seam = int(st.number_input(
        "Min 4-seamers (FF) for VSep", 0, 500, 30, 10,
        help="VSep needs a stable 4-seam IVB.",
    ))
    min_offspeed = int(st.number_input(
        "Min offspeed pitches for VSep", 0, 500, 30, 10,
        help="VSep needs a stable offspeed IVB.",
    ))
    min_swings = int(st.number_input(
        "Min 1st-pitch OS swings (filtered)", 0, 100, 0, 1,
        help="Drop pitchers with fewer than this many qualifying swings *under "
             "the current slicer*. 0 = off.",
    ))
    min_pitches = int(st.number_input(
        "Min 1st-pitch OS pitches (filtered)", 0, 200, 0, 1,
        help="Same idea, for total pitches (CSW% denominator). 0 = off.",
    ))

st.sidebar.markdown("---")
st.sidebar.caption(
    f"**Fastball** = {sorted(FASTBALL_TYPES)}  \n"
    f"**Offspeed** = anything not in {sorted(NON_OFFSPEED)}  \n"
    f"**Whiff %** = swinging strikes / total swings  \n"
    f"**CSW %** = (called strikes + whiffs) / total pitches  \n"
    f"**Lead** = `pitch_number == 1`"
)


# --- Compute ---
result = compute(
    pitch_families=set(selected_families) if not all_families_selected else None,
    location=location,
    platoon=platoon,
    p_throws_filter=p_throws_filter,
    velo_floor=velo_floor,
    min_fastballs=min_fastballs,
    min_4seam=min_4seam,
    min_offspeed=min_offspeed,
    min_swings=min_swings,
    min_pitches=min_pitches,
    divisions=selected_divs,
)


def _slicer_summary():
    parts = []
    if not all_families_selected:
        parts.append("families: " + " / ".join(sorted(selected_families)))
    if location:
        parts.append("zone: " + ("in" if location == "in" else "out"))
    if platoon:
        parts.append("platoon: " + ("same hand" if platoon == "same" else "opp hand"))
    if p_throws_filter:
        parts.append("hand: " + ("RHP" if p_throws_filter == "R" else "LHP"))
    return " · ".join(parts) if parts else "no slicer filters active (all first-pitch offspeed)"


st.caption(
    f"Loaded: {', '.join(result['params']['divisions'])}  "
    f"·  Filters → {_slicer_summary()}"
)


# --- Headline cards ---
def _fmt_rate(value, denom):
    return f"{value}%" if denom else "n/a"


s = result["summary"]
st.header("Headline (current filter)")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Pitchers contributing", s["n_pitchers"],
    help=f"Out of {s['n_eligible_total']} eligible starters under the velo floor / "
         f"min-fastballs gates.",
)
c2.metric("Pitches", f"{s['pitches']:,}")
c3.metric("Swings", f"{s['swings']:,}")
c4.metric("Whiff %", _fmt_rate(s["whiff_rate"], s["swings"]),
          help=f"{s['whiffs']} whiffs / {s['swings']} swings")
c5.metric("CSW %", _fmt_rate(s["csw_rate"], s["pitches"]),
          help=f"{s['whiffs'] + s['called_strikes']} (called + whiffs) / {s['pitches']} pitches")


# --- Breakdowns within the current filter ---
st.header("Breakdowns")
st.caption(
    "Whiff% / CSW% on the same filtered cohort, split across each slicer "
    "dimension. When a dimension is locked by the sidebar, only the matching "
    "row will have data."
)


def _breakdown_df(rows):
    out = []
    for r in rows:
        st_ = r["stats"]
        out.append({
            "": r["label"],
            "Pitchers": r["n_pitchers"],
            "Pitches": st_["pitches"],
            "Swings": st_["swings"],
            "Whiffs": st_["whiffs"],
            "Whiff %": st_["whiff_rate"] if st_["swings"] else None,
            "Called": st_["called_strikes"],
            "CSW %": st_["csw_rate"] if st_["pitches"] else None,
        })
    return pd.DataFrame(out)


bc1, bc2, bc3 = st.columns(3)
with bc1:
    st.subheader("By pitch family")
    st.dataframe(_breakdown_df(result["breakdowns"]["by_family"]),
                 use_container_width=True, hide_index=True)
with bc2:
    st.subheader("By location")
    st.dataframe(_breakdown_df(result["breakdowns"]["by_zone"]),
                 use_container_width=True, hide_index=True)
with bc3:
    st.subheader("By platoon")
    st.dataframe(_breakdown_df(result["breakdowns"]["by_platoon"]),
                 use_container_width=True, hide_index=True)


# --- X-variable distributions & per-pitcher scatter ---
per_pitcher_df = pd.DataFrame([
    {
        "Pitcher": p["name"],
        "Division": p.get("division"),
        "FB velo": p["velo"],
        "FF IVB": p.get("ivb"),
        "OS IVB": p.get("os_ivb"),
        "VSep": p.get("vsep"),
        "Whiff rate": p.get("whiff_rate"),
        "CSW %": p.get("csw_rate"),
        "Pitches": p["fo_pitches"],
        "Swings": p["fo_swings"],
        "Whiffs": p["fo_whiffs"],
        "Called": p["fo_called"],
    }
    for p in result["per_pitcher"]
])

if not per_pitcher_df.empty:
    st.header("X-variable distributions (contributing pitchers)")
    dist_specs = []
    if per_pitcher_df["FB velo"].notna().any():
        dist_specs.append(("FB velo", "mph"))
    if per_pitcher_df["VSep"].notna().any():
        dist_specs.append(("VSep", "in"))

    cols = st.columns(len(dist_specs)) if dist_specs else []
    for col, (field, unit) in zip(cols, dist_specs):
        sub = per_pitcher_df.dropna(subset=[field])
        hist = alt.Chart(sub).mark_bar().encode(
            x=alt.X(f"{field}:Q", bin=alt.Bin(maxbins=20),
                    title=f"{field} ({unit})"),
            y=alt.Y("count()", title="Pitchers"),
            tooltip=[alt.Tooltip(f"{field}:Q", bin=True), "count()"],
        ).properties(height=220)
        col.altair_chart(hist, use_container_width=True)

    st.header("Pitcher scatter")
    metric_choice = st.radio(
        "Y-axis metric", ["Whiff %", "CSW %"],
        index=0, horizontal=True, key="scatter_metric",
    )
    y_col = "Whiff rate" if metric_choice == "Whiff %" else "CSW %"
    size_col = "Swings" if metric_choice == "Whiff %" else "Pitches"

    available_x = [c for c in ["FB velo", "FF IVB", "OS IVB", "VSep"]
                   if per_pitcher_df[c].notna().any()]
    x_field = st.selectbox("X axis", available_x, index=0)

    scatter_df = per_pitcher_df.dropna(subset=[x_field, y_col])
    if scatter_df.empty:
        st.caption("Not enough data to plot at current settings.")
    else:
        scatter = alt.Chart(scatter_df).mark_circle(opacity=0.75).encode(
            x=alt.X(f"{x_field}:Q", scale=alt.Scale(zero=False)),
            y=alt.Y(f"{y_col}:Q", scale=alt.Scale(zero=False),
                    title=f"1st-pitch offspeed {metric_choice}"),
            size=alt.Size(f"{size_col}:Q", scale=alt.Scale(range=[40, 500]),
                          title=f"{size_col} (sample size)"),
            tooltip=["Pitcher", "Division",
                     alt.Tooltip(f"{x_field}:Q", format=".1f"),
                     alt.Tooltip("Whiff rate:Q", format=".1f"),
                     alt.Tooltip("CSW %:Q", format=".1f"),
                     "Pitches", "Swings", "Whiffs", "Called"],
        ).properties(height=420).interactive()
        st.altair_chart(scatter, use_container_width=True)
        st.caption(
            "Bubble size = per-pitcher sample size for the selected metric. "
            "Hover for details. Drag/scroll to zoom."
        )


# --- Regressions ---
def _stars(p):
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    if p < 0.10:  return "."
    return ""


def _render_regression(reg, title, caption, f_help):
    st.header(title)
    st.caption(caption)

    if reg.get("skipped_reason"):
        st.warning(reg["skipped_reason"])
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("N (pitchers)", reg["n"])
    c2.metric("R²", f"{reg['r_squared']:.3f}")
    c3.metric("Adj. R²", f"{reg['adj_r_squared']:.3f}")
    c4.metric("F p-value", f"{reg['f_p_value']:.4f}", help=f_help)
    if reg.get("fit_method"):
        st.caption(
            f"Fit: {reg['fit_method']}"
            + (f" · total weight = {int(reg['total_weight'])} swings"
               if reg.get("total_weight") else "")
        )

    coef_df = pd.DataFrame([
        {
            "Term": c["label"],
            "β (pp)": round(c["coef"], 2),
            "Std err": round(c["std_err"], 2),
            "t": round(c["t"], 2),
            "p": round(c["p_value"], 4),
            "95% CI": f"[{c['ci_lower']:.2f}, {c['ci_upper']:.2f}]",
            "Sig.": _stars(c["p_value"]),
        }
        for c in reg["coefficients"]
    ])
    st.subheader("Coefficients")
    st.dataframe(coef_df, use_container_width=True, hide_index=True)
    st.caption(
        "Significance: `***` p<0.001, `**` p<0.01, `*` p<0.05, `.` p<0.10. "
        "β for `vsep` = pp of whiff% per additional inch of vertical separation."
    )


_render_regression(
    result["regression"],
    title="Regression 1: whiff% ~ vsep (pitcher-level, WLS)",
    caption=(
        "Weighted LS, Y = per-pitcher first-pitch offspeed whiff% under the "
        "current slicer. X of interest: `vsep` (continuous, inches). "
        "Each pitcher weighted by their qualifying swing count."
    ),
    f_help="Test that the vsep slope is zero.",
)

_velo_cut = result["regression_velo"].get("velo_cut", 95.0)
_render_regression(
    result["regression_velo"],
    title=f"Regression 2: whiff% ~ vsep + high_velo (FB ≥ {_velo_cut} mph), pitcher-level WLS",
    caption=(
        f"Weighted LS, Y = whiff% under current slicer. X: `vsep` + "
        f"`high_velo` (1 if avg FB ≥ {_velo_cut} mph, else 0). Adds high-velo "
        f"as a control on top of Regression 1."
    ),
    f_help="Joint test that both slope coefficients (vsep, high_velo) are zero.",
)


# --- Per-pitch detail ---
st.header("Per-pitch detail")
st.caption(
    "One row per first-pitch offspeed pitch in the filtered cohort. Each row "
    "carries the pitcher's `Velo` and `VSep` (the X-vars), the pitch-level "
    "slicer columns (`Pitch family`, `In zone`, `Same hand`), and the outcome "
    "flags (`Swing`, `Whiff`, `Called strike`)."
)

pitch_details_df = pd.DataFrame(result.get("pitch_details", []))
if pitch_details_df.empty:
    st.info("No pitches match the current filter.")
else:
    rename = {
        "pitcher": "Pitcher",
        "division": "Div",
        "game_date": "Date",
        "velo": "Velo (mph)",
        "vsep": "VSep (in)",
        "pitch_type": "Pitch type",
        "pitch_family": "Pitch family",
        "p_throws": "P-hand",
        "stand": "B-stand",
        "in_zone": "In zone",
        "same_hand": "Same hand",
        "description": "Description",
        "swing": "Swing",
        "whiff": "Whiff",
        "called_strike": "Called strike",
    }
    cols_order = [
        "Pitcher", "Div", "Date", "Velo (mph)", "VSep (in)",
        "Pitch type", "Pitch family", "P-hand", "B-stand",
        "Same hand", "In zone", "Description",
        "Swing", "Whiff", "Called strike",
    ]
    display_df = (
        pitch_details_df.drop(columns=["pitcher_id"], errors="ignore")
                        .rename(columns=rename)
                        .reindex(columns=cols_order)
    )
    display_df["Velo (mph)"] = pd.to_numeric(display_df["Velo (mph)"], errors="coerce").round(1)
    display_df["VSep (in)"] = pd.to_numeric(display_df["VSep (in)"], errors="coerce").round(1)

    def _apply_filters(df, pitcher=None, div=None, fam=None, matchup=None):
        out = df
        if pitcher and pitcher != "All":
            out = out[out["Pitcher"] == pitcher]
        if div and div != "All":
            out = out[out["Div"] == div]
        if fam and fam != "All":
            out = out[out["Pitch family"] == fam]
        if matchup and matchup != "All":
            p, b = matchup.split("/")
            out = out[(out["P-hand"] == p) & (out["B-stand"] == b)]
        return out

    def _matchup_opts(df):
        pairs = df[["P-hand", "B-stand"]].dropna().drop_duplicates()
        return sorted(f"{p}/{b}" for p, b in pairs.itertuples(index=False))

    for _k in ("filter_pitcher", "filter_div", "filter_fam", "filter_matchup"):
        st.session_state.setdefault(_k, "All")

    pitcher_pick = st.session_state["filter_pitcher"]
    div_pick = st.session_state["filter_div"]
    fam_pick = st.session_state["filter_fam"]
    matchup_pick = st.session_state["filter_matchup"]

    pitcher_opts = ["All"] + sorted(
        _apply_filters(display_df, div=div_pick, fam=fam_pick, matchup=matchup_pick)
        ["Pitcher"].dropna().unique().tolist()
    )
    div_opts = ["All"] + sorted(
        _apply_filters(display_df, pitcher=pitcher_pick, fam=fam_pick, matchup=matchup_pick)
        ["Div"].dropna().unique().tolist()
    )
    fam_opts = ["All"] + sorted(
        _apply_filters(display_df, pitcher=pitcher_pick, div=div_pick, matchup=matchup_pick)
        ["Pitch family"].dropna().unique().tolist()
    )
    matchup_opts = ["All"] + _matchup_opts(
        _apply_filters(display_df, pitcher=pitcher_pick, div=div_pick, fam=fam_pick)
    )

    if pitcher_pick not in pitcher_opts:
        st.session_state["filter_pitcher"] = "All"
    if div_pick not in div_opts:
        st.session_state["filter_div"] = "All"
    if fam_pick not in fam_opts:
        st.session_state["filter_fam"] = "All"
    if matchup_pick not in matchup_opts:
        st.session_state["filter_matchup"] = "All"

    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        pitcher_pick = st.selectbox("Pitcher", pitcher_opts, key="filter_pitcher")
    with fc2:
        div_pick = st.selectbox("Division", div_opts, key="filter_div")
    with fc3:
        fam_pick = st.selectbox("Pitch family", fam_opts, key="filter_fam")
    with fc4:
        matchup_pick = st.selectbox(
            "Handedness matchup (P/B)", matchup_opts, key="filter_matchup"
        )

    display_df = _apply_filters(
        display_df, pitcher=pitcher_pick, div=div_pick, fam=fam_pick, matchup=matchup_pick
    )
    display_df = display_df.sort_values(["Pitcher", "Date"], na_position="last")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.caption(f"{len(display_df):,} pitch rows.")


# --- Below-velo-floor list ---
if result["excluded_below_floor"]:
    with st.expander(
        f"Pitchers excluded by velo floor ({len(result['excluded_below_floor'])})"
    ):
        df = pd.DataFrame(result["excluded_below_floor"]).drop(columns=["id"])
        df["velo"] = df["velo"].round(1)
        st.dataframe(
            df.rename(columns={"name": "Pitcher", "velo": "Avg FB velo"}),
            use_container_width=True, hide_index=True,
        )

st.caption(
    "Source: cached Statcast pulls in `data/{division}_starters_*_pitches.parquet`. "
    "Starters with > 3 GS only."
)
