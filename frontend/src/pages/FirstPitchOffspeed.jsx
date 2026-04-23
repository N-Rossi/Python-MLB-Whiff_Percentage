import { useEffect, useMemo, useRef, useState } from "react";
import Sidebar from "../components/Sidebar.jsx";
import Metric from "../components/Metric.jsx";
import BreakdownTable from "../components/BreakdownTable.jsx";
import Histogram from "../components/Histogram.jsx";
import PitcherScatter from "../components/Scatter.jsx";
import TraitsTable from "../components/TraitsTable.jsx";
import PitchDetailTable from "../components/PitchDetailTable.jsx";
import {
  computeFirstPitchOffspeed,
  getDivisions,
  getFirstPitchOffspeedMeta,
} from "../api.js";

function fmtRate(val, denom) {
  if (!denom) return "n/a";
  return `${val}%`;
}

function slicerSummary(state, offspeedTypes) {
  const parts = [];
  const allTypes =
    state.pitchTypes.length === offspeedTypes.length &&
    offspeedTypes.every((t) => state.pitchTypes.includes(t));
  if (!allTypes && state.pitchTypes.length) {
    parts.push("pitch types: " + [...state.pitchTypes].sort().join(" / "));
  }
  if (state.location)
    parts.push("zone: " + (state.location === "in" ? "in" : "out"));
  if (state.platoon)
    parts.push(
      "platoon: " + (state.platoon === "same" ? "same hand" : "opp hand")
    );
  if (state.pThrows)
    parts.push("hand: " + (state.pThrows === "R" ? "RHP" : "LHP"));
  return parts.length
    ? parts.join(" · ")
    : "no slicer filters active (all first-pitch offspeed)";
}

export default function FirstPitchOffspeed() {
  const [meta, setMeta] = useState(null);
  const [hasData, setHasData] = useState(null);
  const [bootError, setBootError] = useState(null);

  const [state, setState] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [scatterMetric, setScatterMetric] = useState("Whiff %");
  const [scatterX, setScatterX] = useState("FB velo");

  useEffect(() => {
    Promise.all([getFirstPitchOffspeedMeta(), getDivisions()])
      .then(([m, d]) => {
        setMeta(m);
        setHasData(d.divisions.length > 0);
        setState({
          pitchTypes: [...m.offspeed_pitch_types],
          location: null,
          platoon: null,
          pThrows: null,
          useVeloFloor: true,
          veloFloor: 90.9,
          minFastballs: 50,
          min4seam: 30,
          minOffspeed: 30,
          minSwings: 0,
          minPitches: 0,
        });
      })
      .catch((e) => setBootError(e.message));
  }, []);

  // Re-compute whenever state changes (debounced).
  const debounceRef = useRef();
  useEffect(() => {
    if (!state || state.pitchTypes.length === 0) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      setError(null);
      const allTypes =
        state.pitchTypes.length === meta.offspeed_pitch_types.length;
      computeFirstPitchOffspeed({
        pitch_types: allTypes ? null : state.pitchTypes,
        location: state.location,
        platoon: state.platoon,
        p_throws_filter: state.pThrows,
        velo_floor: state.useVeloFloor ? state.veloFloor : null,
        min_fastballs: state.minFastballs,
        min_4seam: state.min4seam,
        min_offspeed: state.minOffspeed,
        min_swings: state.minSwings,
        min_pitches: state.minPitches,
        divisions: null,
      })
        .then(setResult)
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(debounceRef.current);
  }, [state, meta]);

  const perPitcherDf = useMemo(() => {
    if (!result) return [];
    return result.per_pitcher.map((p) => ({
      Pitcher: p.name,
      Division: p.division,
      "FB velo": p.velo,
      "FB IVB": p.ivb,
      "OS IVB": p.os_ivb,
      "VSep": p.vsep,
      "Whiff rate": p.whiff_rate,
      "CSW %": p.csw_rate,
      Pitches: p.fo_pitches,
      Swings: p.fo_swings,
      Whiffs: p.fo_whiffs,
      Called: p.fo_called,
    }));
  }, [result]);

  if (bootError) {
    return (
      <div className="legacy-page">
        <div className="error">
          Failed to load metadata: {bootError}
          <br />
          Is the backend running? Start it with{" "}
          <code>uvicorn backend.main:app --reload --port 8000</code>
        </div>
      </div>
    );
  }
  if (!meta || !state || hasData == null) {
    return (
      <div className="legacy-page">
        <div className="loading">Loading…</div>
      </div>
    );
  }
  if (!hasData) {
    return (
      <div className="legacy-page">
        <div className="error">
          No pitch data found in <code>data/</code>.
          <br />
          Run <code>python fetch_starters.py &lt;division&gt;</code> first to
          populate the cache. Use <code>all</code> to fetch every division.
        </div>
      </div>
    );
  }

  const needPitchTypes = state.pitchTypes.length === 0;

  // Pre-compute which x-axis fields are available for the scatter.
  const availableX = ["FB velo", "FB IVB", "OS IVB", "VSep"].filter((f) =>
    perPitcherDf.some((r) => r[f] != null)
  );
  if (availableX.length && !availableX.includes(scatterX)) {
    // reset to first available
    setTimeout(() => setScatterX(availableX[0]), 0);
  }

  const yCol = scatterMetric === "Whiff %" ? "Whiff rate" : "CSW %";
  const sizeCol = scatterMetric === "Whiff %" ? "Swings" : "Pitches";
  const scatterData = perPitcherDf.filter(
    (d) => d[scatterX] != null && d[yCol] != null
  );

  const veloValues = perPitcherDf
    .map((r) => r["FB velo"])
    .filter((v) => v != null);
  const vsepValues = perPitcherDf
    .map((r) => r["VSep"])
    .filter((v) => v != null);

  return (
    <div className="legacy-page">
    <div className="layout">
      <Sidebar state={state} setState={setState} meta={meta} />

      <div className="content">
        <h1>First-Pitch Offspeed — MLB Starters</h1>

        {needPitchTypes && (
          <div className="warning">
            Pick at least one pitch type in the sidebar.
          </div>
        )}

        {error && <div className="error">{error}</div>}

        {result && (
          <>
            <div className="caption">
              Loaded: {result.params.divisions.join(", ")} · Filters →{" "}
              {slicerSummary(state, meta.offspeed_pitch_types)}
              {loading && " · computing…"}
            </div>

            <h2>Headline (current filter)</h2>
            <div className="metrics">
              <Metric
                label="Pitchers contributing"
                value={result.summary.n_pitchers}
                help={`Out of ${result.summary.n_eligible_total} eligible starters under the velo floor / min-fastballs gates.`}
              />
              <Metric
                label="Pitches"
                value={result.summary.pitches.toLocaleString()}
              />
              <Metric
                label="Swings"
                value={result.summary.swings.toLocaleString()}
              />
              <Metric
                label="Whiff %"
                value={fmtRate(
                  result.summary.whiff_rate,
                  result.summary.swings
                )}
                help={`${result.summary.whiffs} whiffs / ${result.summary.swings} swings`}
              />
              <Metric
                label="CSW %"
                value={fmtRate(
                  result.summary.csw_rate,
                  result.summary.pitches
                )}
                help={`${
                  result.summary.whiffs + result.summary.called_strikes
                } (called + whiffs) / ${result.summary.pitches} pitches`}
              />
            </div>

            <h2>Breakdowns</h2>
            <div className="caption">
              Whiff% / CSW% on the same filtered cohort, split across each
              slicer dimension. When a dimension is locked by the sidebar, only
              the matching row will have data.
            </div>
            <div className="columns">
              <BreakdownTable
                title="By pitch type"
                rows={result.breakdowns.by_pitch_type}
              />
              <BreakdownTable
                title="By location"
                rows={result.breakdowns.by_zone}
              />
              <BreakdownTable
                title="By platoon"
                rows={result.breakdowns.by_platoon}
              />
            </div>

            {perPitcherDf.length > 0 && (
              <>
                <h2>X-variable distributions (contributing pitchers)</h2>
                <div className="columns" style={{ gridTemplateColumns: "1fr 1fr" }}>
                  {veloValues.length > 0 && (
                    <Histogram
                      title="FB velo"
                      unit="mph"
                      values={veloValues}
                    />
                  )}
                  {vsepValues.length > 0 && (
                    <Histogram title="VSep" unit="in" values={vsepValues} />
                  )}
                </div>

                <h2>Pitcher scatter</h2>
                <div className="filter-row cols-2">
                  <div>
                    <label>Y-axis metric</label>
                    <div className="radio-row">
                      {["Whiff %", "CSW %"].map((m) => (
                        <button
                          key={m}
                          type="button"
                          className={scatterMetric === m ? "active" : ""}
                          onClick={() => setScatterMetric(m)}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label>X axis</label>
                    <select
                      value={scatterX}
                      onChange={(e) => setScatterX(e.target.value)}
                    >
                      {availableX.map((f) => (
                        <option key={f} value={f}>
                          {f}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <PitcherScatter
                  data={scatterData}
                  xField={scatterX}
                  yField={yCol}
                  sizeField={sizeCol}
                  xLabel={scatterX}
                  yLabel={`1st-pitch offspeed ${scatterMetric}`}
                  sizeLabel={`${sizeCol} (sample size)`}
                />
                <div className="caption">
                  Bubble size = per-pitcher sample size for the selected
                  metric. Hover for details.
                </div>
              </>
            )}

            <h2>Per-pitcher trait table</h2>
            <div className="caption">
              One row per eligible pitcher. FB traits (velo / IVB / arm-side
              break / spin / extension / usage %) plus FB→OS deception
              separations (ΔV, VSep, HSep, release separation). Whiff % here is
              first-pitch offspeed under the current sidebar slicer; the trait
              columns themselves are season-long and do not move with the
              slicer.
            </div>
            <TraitsTable rows={result.pitcher_traits || []} />

            <h2>Per-pitch detail</h2>
            <div className="caption">
              One row per first-pitch offspeed pitch in the filtered cohort.
              Each row carries the pitcher's Velo and VSep (the X-vars), the
              pitch-level slicer columns (Pitch type, In zone, Same hand), and
              the outcome flags (Swing, Whiff, Called strike).
            </div>
            <PitchDetailTable
              rows={result.pitch_details || []}
              pitchTypeLabels={meta.pitch_type_labels}
            />

            {result.excluded_below_floor.length > 0 && (
              <details className="expander" style={{ marginTop: 16 }}>
                <summary>
                  Pitchers excluded by velo floor (
                  {result.excluded_below_floor.length})
                </summary>
                <div>
                  <table>
                    <thead>
                      <tr>
                        <th>Pitcher</th>
                        <th>Avg FB velo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.excluded_below_floor.map((r) => (
                        <tr key={r.id}>
                          <td>{r.name}</td>
                          <td>{r.velo.toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}

            <div className="caption" style={{ marginTop: 20 }}>
              Source: cached Statcast pulls in{" "}
              <code>data/{"{division}"}_starters_*_pitches.parquet</code>.
              Starters with &gt; 3 GS only.
            </div>
          </>
        )}

        {loading && !result && <div className="loading">Computing…</div>}
      </div>
    </div>
    </div>
  );
}
