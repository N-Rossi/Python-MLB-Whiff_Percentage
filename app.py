"""
Streamlit UI for the velo + IVB whiff-rate analysis.

Run:
    pip install streamlit
    streamlit run multi/app.py
"""

import altair as alt
import pandas as pd
import streamlit as st

from analyze_pitches import (
    compute_buckets,
    available_divisions,
    FASTBALL_TYPES,
    NON_OFFSPEED,
)

st.set_page_config(page_title="MLB Pitch Analysis", layout="wide")
st.title("First-Pitch Offspeed Whiff Rate — MLB Starters")

divs = available_divisions()
if not divs:
    st.error(
        "No pitch data found in `multi/`.\n\n"
        "Run `python multi/fetch_starters.py <division>` first to populate the cache. "
        "Use `all` to fetch every division."
    )
    st.stop()


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
    90.0, 100.0, 94.9, 0.1,
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
    help="Per-pitcher gate: drop pitchers with fewer first-pitch offspeed swings than this. Useful for cleaning up the scatter / roster of small-sample noise.",
)

st.sidebar.markdown("---")
st.sidebar.caption(
    f"**Fastball** = {sorted(FASTBALL_TYPES)}  \n"
    f"**Offspeed** = anything not in {sorted(NON_OFFSPEED)}  \n"
    f"**Whiff rate** = swinging strikes / total swings  \n"
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
    divisions=selected_divs,
)

st.caption("Loaded: " + ", ".join(result["params"]["divisions"]))


def _whiff_pct(stats):
    return f"{stats['whiff_rate']}%" if stats["swings"] else "n/a"


def _bucket_card(col, bucket):
    s = bucket["stats"]
    col.subheader(bucket["label"])
    col.metric("Whiff rate", _whiff_pct(s),
               help=f"{s['whiffs']} whiffs / {s['swings']} swings")
    col.caption(f"{len(bucket['roster'])} pitchers · {s['pitches']} pitches · {s['swings']} swings")


def _render_comparison(cmp):
    st.header(cmp["title"])
    n = len(cmp["buckets"])
    if n == 2:
        c1, c2, c3 = st.columns([2, 2, 1])
        _bucket_card(c1, cmp["buckets"][0])
        _bucket_card(c2, cmp["buckets"][1])
        sa, sb = cmp["buckets"][0]["stats"], cmp["buckets"][1]["stats"]
        if sa["swings"] and sb["swings"]:
            diff = sa["whiff_rate"] - sb["whiff_rate"]
            verdict = "higher" if diff > 0 else ("lower" if diff < 0 else "equal")
            c3.metric(cmp.get("delta_label", "Δ"), f"{diff:+.1f} pp",
                      help=f"{cmp['buckets'][0]['label']} is {abs(diff):.1f} pp {verdict} than {cmp['buckets'][1]['label']}")
    else:
        cols = st.columns(max(n, 1))
        for col, bucket in zip(cols, cmp["buckets"]):
            _bucket_card(col, bucket)

    if cmp.get("excluded_note"):
        st.caption(cmp["excluded_note"])


for cmp in result["comparisons"]:
    _render_comparison(cmp)


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
                "Swings": p["fo_swings"],
                "Whiffs": p["fo_whiffs"],
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

    scatter_df = pitchers_df.dropna(subset=[x_field, "Whiff rate"])
    if scatter_df.empty:
        st.caption("Not enough data to plot at current settings.")
    else:
        scatter = alt.Chart(scatter_df).mark_circle(opacity=0.75).encode(
            x=alt.X(f"{x_field}:Q", scale=alt.Scale(zero=False)),
            y=alt.Y("Whiff rate:Q", title="1st-pitch offspeed whiff %",
                    scale=alt.Scale(zero=False)),
            size=alt.Size("Swings:Q", title="Swings (sample size)",
                          scale=alt.Scale(range=[40, 500])),
            color=alt.Color("Bucket:N"),
            tooltip=["Pitcher", "Bucket", "Division",
                     alt.Tooltip(f"{x_field}:Q", format=".1f"),
                     alt.Tooltip("Whiff rate:Q", format=".1f"),
                     "Whiffs", "Swings"],
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
        st.caption("Bubble size = # of first-pitch offspeed swings (per-pitcher sample size). "
                   "Hover for details. Drag/scroll to zoom.")

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
    df["fo_sample"] = df.apply(
        lambda r: f"{int(r['fo_whiffs'])}/{int(r['fo_swings'])}", axis=1
    )
    rename = {
        "name": "Pitcher",
        "division": "Div",
        "velo": "Avg FB velo",
        "ivb": "Avg FF IVB (in)",
        "os_ivb": "Avg OS IVB (in)",
        "vsep": "VSep (in)",
        "whiff_rate": "1st-pitch OS whiff %",
        "fo_sample": "Whiffs / swings",
    }
    return (
        df.rename(columns=rename)
          .drop(columns=["id", "fo_pitches", "fo_swings", "fo_whiffs"])
          [["Pitcher", "Div", "Avg FB velo", "Avg FF IVB (in)", "Avg OS IVB (in)",
            "VSep (in)", "1st-pitch OS whiff %", "Whiffs / swings"]]
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

st.caption("Source: cached Statcast pulls in `multi/{division}_starters_*_pitches.csv`. Starters with > 3 GS only.")
