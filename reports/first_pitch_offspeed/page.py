"""
Streamlit page for the velo + IVB + CSW%/whiff-rate analysis.
Loaded by home.py via st.navigation.
"""

import altair as alt
import pandas as pd
import streamlit as st

from reports.first_pitch_offspeed.analyze import (
    compute_buckets,
    available_divisions,
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


# Metric router. CSW% denominator is total pitches; whiff% denominator is swings,
# so the per-pitcher sample-size column and the Δ-eligibility gate both shift.
METRICS = {
    "CSW%": {
        "rate_key": "csw_rate",
        "axis_title": "1st-pitch offspeed CSW %",
        "card_label": "CSW %",
        "stat_gate": "pitches",
        "sample_key": "fo_pitches",
        "sample_title": "Pitches (sample size)",
        "tooltip_label": "CSW %",
        "numer_label": "called + whiffs",
        "denom_label": "pitches",
        "numer_of": lambda s: s["whiffs"] + s["called_strikes"],
        "denom_of": lambda s: s["pitches"],
    },
    "Whiff %": {
        "rate_key": "whiff_rate",
        "axis_title": "1st-pitch offspeed whiff %",
        "card_label": "Whiff %",
        "stat_gate": "swings",
        "sample_key": "fo_swings",
        "sample_title": "Swings (sample size)",
        "tooltip_label": "Whiff %",
        "numer_label": "whiffs",
        "denom_label": "swings",
        "numer_of": lambda s: s["whiffs"],
        "denom_of": lambda s: s["swings"],
    },
}


def _toggle_slider(key, label, default_on, *args, help=None, **kwargs):
    """Render an enable-checkbox + slider pair. Returns the slider value
    when the checkbox is on, else None."""
    on = st.sidebar.checkbox(f"Use {label}", value=default_on, key=f"{key}_on")
    val = st.sidebar.slider(label, *args, **kwargs, key=key, disabled=not on, help=help)
    return val if on else None


def _toggle_int(key, label, default_on, *args, help=None, **kwargs):
    on = st.sidebar.checkbox(f"Use {label}", value=default_on, key=f"{key}_on")
    val = st.sidebar.number_input(label, *args, **kwargs, key=key, disabled=not on, help=help)
    return int(val) if on else 0


# --- Sidebar ---
st.sidebar.header("Primary metric")
metric_choice = st.sidebar.radio(
    "Headline / scatter / Δ uses…",
    list(METRICS.keys()),
    index=0,
    horizontal=True,
    help="Both metrics are always shown in cards and rosters. This toggle "
         "controls which one drives the bucket Δ comparison and the scatter "
         "Y-axis.\n\nCSW% = (called strikes + whiffs) / total pitches.\n"
         "Whiff% = whiffs / total swings.",
)
M = METRICS[metric_choice]

st.sidebar.header("Divisions")
selected_divs = st.sidebar.multiselect(
    "Include data from", options=divs, default=divs,
    help="Pick which cached divisions to roll into the analysis"
)
if not selected_divs:
    st.warning("Select at least one division in the sidebar.")
    st.stop()

st.sidebar.header("Filters (uncheck to ignore)")
velo_threshold = _toggle_slider(
    "velo_thr", "Velo threshold (mph)", True,
    90.0, 100.0, 95.0, 0.1,
    help="Pitchers with avg fastball >= this go in the 'high-velo' bucket. Disable to skip the high/low split.",
)
velo_floor = _toggle_slider(
    "velo_flr", "Velo floor (mph)", True,
    85.0, 95.0, 90.9, 0.1,
    help="Drop pitchers averaging below this — keeps junk-ballers out. Disable to include everyone.",
)
vsep_threshold = _toggle_slider(
    "vsep", "Vertical separation threshold (in)", True,
    5.0, 30.0, 18.0, 0.5,
    help="Sub-split by avg 4-seam IVB minus avg offspeed IVB. Larger = more vertical contrast between fastball and offspeed. Disable to skip this split.",
)

st.sidebar.header("Sample-size gates (uncheck to ignore)")
min_fastballs = _toggle_int(
    "min_fb", "Min fastballs (FF/SI/FT)", True, 0, 500, 50, 10,
    help="Pitchers with fewer fastballs are dropped (sample too small for a stable velo).",
)
min_4seam = _toggle_int(
    "min_ff", "Min 4-seamers (FF) for IVB", True, 0, 500, 30, 10,
    help="Pitchers with fewer 4-seamers get excluded from the FF IVB split.",
)
min_offspeed = _toggle_int(
    "min_os", "Min offspeed pitches for OS IVB", True, 0, 500, 30, 10,
    help="Pitchers with fewer offspeed pitches get excluded from the offspeed IVB split.",
)
min_swings = _toggle_int(
    "min_sw", "Min 1st-pitch offspeed swings", False, 0, 100, 5, 1,
    help="Per-pitcher gate for whiff% sample size. Drop pitchers with fewer first-pitch offspeed swings than this.",
)
min_pitches = _toggle_int(
    "min_p", "Min 1st-pitch offspeed pitches", False, 0, 200, 10, 1,
    help="Per-pitcher gate for CSW% sample size. Drop pitchers with fewer first-pitch offspeed pitches than this.",
)

st.sidebar.markdown("---")
st.sidebar.caption(
    f"**Fastball** = {sorted(FASTBALL_TYPES)}  \n"
    f"**Offspeed** = anything not in {sorted(NON_OFFSPEED)}  \n"
    f"**Whiff %** = swinging strikes / total swings  \n"
    f"**CSW %** = (called strikes + whiffs) / total pitches  \n"
    f"**Lead** = `pitch_number == 1`"
)

# --- Compute ---
result = compute_buckets(
    velo_threshold=velo_threshold,
    velo_floor=velo_floor,
    vsep_threshold=vsep_threshold,
    min_fastballs=min_fastballs,
    min_4seam=min_4seam,
    min_offspeed=min_offspeed,
    min_swings=min_swings,
    min_pitches=min_pitches,
    divisions=selected_divs,
)

st.caption("Loaded: " + ", ".join(result["params"]["divisions"]))


def _fmt_rate(value, denom):
    return f"{value}%" if denom else "n/a"


def _bucket_card(col, bucket):
    """Show both metrics; primary (per toggle) goes in the big st.metric slot."""
    s = bucket["stats"]
    col.subheader(bucket["label"])

    csw_str = _fmt_rate(s["csw_rate"], s["pitches"])
    csw_help = f"{s['whiffs'] + s['called_strikes']} (called + whiffs) / {s['pitches']} pitches"
    whiff_str = _fmt_rate(s["whiff_rate"], s["swings"])
    whiff_help = f"{s['whiffs']} whiffs / {s['swings']} swings"

    if M["rate_key"] == "csw_rate":
        col.metric("CSW %", csw_str, help=csw_help)
        col.caption(f"Whiff %: **{whiff_str}**  ({s['whiffs']} / {s['swings']})")
    else:
        col.metric("Whiff %", whiff_str, help=whiff_help)
        col.caption(f"CSW %: **{csw_str}**  ({s['whiffs'] + s['called_strikes']} / {s['pitches']})")

    col.caption(
        f"{len(bucket['roster'])} pitchers · "
        f"{s['pitches']} pitches · {s['swings']} swings · {s['called_strikes']} called"
    )


def _render_comparison(cmp):
    st.header(cmp["title"])
    n = len(cmp["buckets"])
    if n == 2:
        c1, c2, c3 = st.columns([2, 2, 1])
        a, b = cmp["buckets"]
        _bucket_card(c1, a)
        _bucket_card(c2, b)
        sa, sb = a["stats"], b["stats"]
        gate = M["stat_gate"]
        if sa[gate] and sb[gate]:
            diff = sa[M["rate_key"]] - sb[M["rate_key"]]
            verdict = "higher" if diff > 0 else ("lower" if diff < 0 else "equal")
            c3.metric(
                cmp.get("delta_label", "Δ"),
                f"{diff:+.1f} pp",
                help=f"{M['card_label']}: {a['label']} is {abs(diff):.1f} pp "
                     f"{verdict} than {b['label']}",
            )
    else:
        cols = st.columns(max(n, 1))
        for col, bucket in zip(cols, cmp["buckets"]):
            _bucket_card(col, bucket)

    if cmp.get("excluded_note"):
        st.caption(cmp["excluded_note"])


for cmp in result["comparisons"]:
    _render_comparison(cmp)


# --- Regression ---
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
    c1.metric("N", reg["n"])
    c2.metric("R²", f"{reg['r_squared']:.3f}")
    c3.metric("Adj. R²", f"{reg['adj_r_squared']:.3f}")
    c4.metric("F p-value", f"{reg['f_p_value']:.4f}", help=f_help)

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
    st.caption("Significance: `***` p<0.001, `**` p<0.01, `*` p<0.05, `.` p<0.10. "
               "β for `vsep` = pp of whiff% per additional inch of vertical separation. "
               "Each row shows its own standard error and p-value.")


_render_regression(
    result["regression"],
    title="Regression 1: whiff% ~ vsep",
    caption=(
        "OLS, Y = per-pitcher first-pitch offspeed whiff%. "
        "X of interest: `vsep` (continuous, inches). No controls. "
        "Same eligible pitchers as the buckets above."
    ),
    f_help="Test that the vsep slope is zero.",
)

_velo_cut = result["regression_velo"].get("velo_cut", 95.0)
_render_regression(
    result["regression_velo"],
    title=f"Regression 2: whiff% ~ vsep + high_velo (FB ≥ {_velo_cut} mph)",
    caption=(
        f"OLS, Y = whiff%. X: `vsep` (continuous, inches) + `high_velo` "
        f"(1 if avg FB ≥ {_velo_cut} mph, else 0). Adds high-velo as a control "
        f"to Regression 1 — compare the vsep coefficient across the two fits."
    ),
    f_help="Joint test that both slope coefficients (vsep, high_velo) are zero.",
)


# --- Pitcher-level visuals ---
def _all_pitchers_df(result):
    """Flatten the first comparison's buckets into one row per pitcher.
    The first comparison covers every eligible pitcher (high+low velo, or
    one big 'All eligible' bucket if velo is disabled), so each pitcher
    appears exactly once with their primary bucket as their color group."""
    if not result["comparisons"]:
        return pd.DataFrame()
    rows = []
    for bucket in result["comparisons"][0]["buckets"]:
        for p in bucket["roster"]:
            rows.append({
                "Pitcher": p["name"],
                "Bucket": bucket["label"],
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
            })
    return pd.DataFrame(rows)


pitchers_df = _all_pitchers_df(result)

if not pitchers_df.empty:
    st.header("Distributions")
    p = result["params"]
    dist_cols = []
    if "FB velo" in pitchers_df.columns:
        dist_cols.append(("FB velo", p.get("velo_threshold"), "mph"))
    if pitchers_df["VSep"].notna().any():
        dist_cols.append(("VSep", p.get("vsep_threshold"), "in"))

    cols = st.columns(len(dist_cols)) if dist_cols else []
    for col, (field, threshold, unit) in zip(cols, dist_cols):
        sub = pitchers_df.dropna(subset=[field])
        hist = alt.Chart(sub).mark_bar().encode(
            x=alt.X(f"{field}:Q", bin=alt.Bin(maxbins=20),
                    title=f"{field} ({unit})"),
            y=alt.Y("count()", title="Pitchers"),
            tooltip=[alt.Tooltip(f"{field}:Q", bin=True), "count()"],
        ).properties(height=220)
        layers = [hist]
        if threshold is not None:
            rule = alt.Chart(pd.DataFrame({"x": [threshold]})).mark_rule(
                color="red", strokeDash=[6, 4], size=2
            ).encode(x="x:Q",
                     tooltip=[alt.Tooltip("x:Q", title=f"{field} threshold")])
            layers.append(rule)
        col.altair_chart(alt.layer(*layers), use_container_width=True)

    st.header("Pitcher scatter")
    available_x = [
        c for c in ["FB velo", "FF IVB", "OS IVB", "VSep"]
        if pitchers_df[c].notna().any()
    ]
    x_field = st.selectbox("X axis", available_x, index=0)

    # Map metric -> the column in pitchers_df
    y_col_map = {"csw_rate": "CSW %", "whiff_rate": "Whiff rate"}
    y_col = y_col_map[M["rate_key"]]
    size_col_map = {"csw_rate": "Pitches", "whiff_rate": "Swings"}
    size_col = size_col_map[M["rate_key"]]

    scatter_df = pitchers_df.dropna(subset=[x_field, y_col])
    if scatter_df.empty:
        st.caption("Not enough data to plot at current settings.")
    else:
        scatter = alt.Chart(scatter_df).mark_circle(opacity=0.75).encode(
            x=alt.X(f"{x_field}:Q", scale=alt.Scale(zero=False)),
            y=alt.Y(f"{y_col}:Q", title=M["axis_title"],
                    scale=alt.Scale(zero=False)),
            size=alt.Size(f"{size_col}:Q", title=M["sample_title"],
                          scale=alt.Scale(range=[40, 500])),
            color=alt.Color("Bucket:N"),
            tooltip=["Pitcher", "Bucket", "Division",
                     alt.Tooltip(f"{x_field}:Q", format=".1f"),
                     alt.Tooltip("CSW %:Q", format=".1f"),
                     alt.Tooltip("Whiff rate:Q", format=".1f"),
                     "Pitches", "Swings", "Whiffs", "Called"],
        ).properties(height=420).interactive()

        # Add a vertical reference line for the active threshold on this axis
        threshold_map = {
            "FB velo": result["params"].get("velo_threshold"),
            "VSep":    result["params"].get("vsep_threshold"),
        }
        thr = threshold_map.get(x_field)
        if thr is not None:
            rule = alt.Chart(pd.DataFrame({"x": [thr]})).mark_rule(
                color="red", strokeDash=[6, 4]
            ).encode(x="x:Q")
            scatter = scatter + rule

        st.altair_chart(scatter, use_container_width=True)
        st.caption(
            f"Bubble size = # of first-pitch offspeed {M['denom_label']} "
            f"(per-pitcher sample size for {M['card_label']}). "
            "Hover for details. Drag/scroll to zoom."
        )

# --- Rosters ---
st.header("Bucket rosters")


def _roster_df(roster):
    if not roster:
        return pd.DataFrame()
    df = pd.DataFrame(roster)
    for col in ("velo", "ivb", "os_ivb", "vsep"):
        if col in df.columns:
            # Convert None -> NaN so .round() doesn't choke on object dtype
            df[col] = pd.to_numeric(df[col], errors="coerce").round(1)
    df["whiff_sample"] = df.apply(
        lambda r: f"{int(r['fo_whiffs'])}/{int(r['fo_swings'])}", axis=1
    )
    df["csw_sample"] = df.apply(
        lambda r: f"{int(r['fo_whiffs']) + int(r['fo_called'])}/{int(r['fo_pitches'])}",
        axis=1,
    )
    rename = {
        "name": "Pitcher",
        "division": "Div",
        "velo": "Avg FB velo",
        "ivb": "Avg FF IVB (in)",
        "os_ivb": "Avg OS IVB (in)",
        "vsep": "VSep (in)",
        "whiff_rate": "1st-pitch OS whiff %",
        "csw_rate": "1st-pitch OS CSW %",
        "whiff_sample": "Whiffs / swings",
        "csw_sample": "(Called + whiffs) / pitches",
    }
    return (
        df.rename(columns=rename)
          .drop(columns=["id", "fo_pitches", "fo_swings", "fo_whiffs", "fo_called"])
          [["Pitcher", "Div", "Avg FB velo", "Avg FF IVB (in)", "Avg OS IVB (in)",
            "VSep (in)",
            "1st-pitch OS CSW %", "(Called + whiffs) / pitches",
            "1st-pitch OS whiff %", "Whiffs / swings"]]
    )


# Build one tab per unique bucket label across all comparisons,
# plus tabs for any "excluded" rosters and the below-floor list.
tab_labels = []
tab_rosters = []
seen = set()
for cmp in result["comparisons"]:
    for bucket in cmp["buckets"]:
        if bucket["label"] in seen:
            continue
        seen.add(bucket["label"])
        tab_labels.append(bucket["label"])
        tab_rosters.append(bucket["roster"])
    if cmp.get("excluded_roster"):
        label = f"Excluded: {cmp['title']}"
        tab_labels.append(label)
        tab_rosters.append(cmp["excluded_roster"])

if result["excluded_below_floor"]:
    tab_labels.append("Below velo floor")
    tab_rosters.append(None)  # special-case below

if tab_labels:
    tabs = st.tabs(tab_labels)
    for tab, label, roster in zip(tabs, tab_labels, tab_rosters):
        with tab:
            if label == "Below velo floor":
                df = pd.DataFrame(result["excluded_below_floor"]).drop(columns=["id"])
                df["velo"] = df["velo"].round(1)
                st.dataframe(df.rename(columns={"name": "Pitcher", "velo": "Avg FB velo"}),
                             use_container_width=True, hide_index=True)
            else:
                st.dataframe(_roster_df(roster), use_container_width=True, hide_index=True)

st.caption("Source: cached Statcast pulls in `data/{division}_starters_*_pitches.parquet`. Starters with > 3 GS only.")
