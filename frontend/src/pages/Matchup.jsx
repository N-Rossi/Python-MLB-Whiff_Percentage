import { useEffect, useRef, useState } from "react";
import EdgeTable from "../components/EdgeTable.jsx";
import Metric from "../components/Metric.jsx";
import PlayerCombo from "../components/PlayerCombo.jsx";
import {
  getMatchupPairing,
  getSeasons,
  getTopEdges,
  searchBatters,
  searchPitchers,
} from "../api.js";

function fmtWeighted(x) {
  if (x == null) return "—";
  return (x * 1000).toFixed(2);
}
function fmtLiftPP(x) {
  if (x == null) return "—";
  return (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + " pp";
}

export default function Matchup() {
  const [seasons, setSeasons] = useState([]);
  const [season, setSeason] = useState(null);
  const [pitcher, setPitcher] = useState(null);
  const [batter, setBatter] = useState(null);

  const [minPitcherN, setMinPitcherN] = useState(0);
  const [minBatterSwings, setMinBatterSwings] = useState(0);

  const [pairing, setPairing] = useState(null);
  const [topEdges, setTopEdges] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [bootError, setBootError] = useState(null);

  useEffect(() => {
    getSeasons()
      .then((s) => {
        setSeasons(s.seasons);
        setSeason(s.seasons[0]);
      })
      .catch((e) => setBootError(e.message));
  }, []);

  // Fetch when both players chosen -> pairing card; otherwise fetch a
  // league-wide top edges preview so the page isn't empty while the user
  // is making selections.
  const debRef = useRef();
  useEffect(() => {
    if (!season) return;
    clearTimeout(debRef.current);
    debRef.current = setTimeout(() => runQuery(), 200);
    return () => clearTimeout(debRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, pitcher, batter, minPitcherN, minBatterSwings]);

  function runQuery() {
    setError(null);
    setLoading(true);
    if (pitcher && batter) {
      setTopEdges(null);
      getMatchupPairing(pitcher.id, batter.id, {
        season,
        min_pitcher_n: minPitcherN,
        min_batter_swings: minBatterSwings,
      })
        .then(setPairing)
        .catch((e) => {
          setPairing(null);
          setError(e.message);
        })
        .finally(() => setLoading(false));
    } else {
      // No pair yet — show top league edges as a browsing aid. Respect whichever
      // single player is picked.
      setPairing(null);
      getTopEdges({
        season,
        pitcher_id: pitcher?.id,
        batter_id: batter?.id,
        min_pitcher_n: Math.max(minPitcherN, 50),
        min_batter_swings: Math.max(minBatterSwings, 30),
        limit: 50,
      })
        .then((d) => setTopEdges(d.rows))
        .catch((e) => {
          setTopEdges(null);
          setError(e.message);
        })
        .finally(() => setLoading(false));
    }
  }

  if (bootError) {
    return <div className="error">Failed to load API metadata: {bootError}</div>;
  }
  if (!season) return <div className="loading">Loading…</div>;

  const lowerSampleFloor = !pitcher || !batter
    ? "Default floors (pitcher_n≥50, batter_swings≥30) while browsing; drop them in sidebar for less-common pairs."
    : null;

  return (
    <div className="layout">
      <div className="sidebar">
        <h3>Matchup</h3>
        <label>Season</label>
        <select value={season} onChange={(e) => setSeason(Number(e.target.value))}>
          {seasons.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <PlayerCombo
          label="Pitcher"
          value={pitcher}
          onChange={setPitcher}
          fetchPlayers={(q) => searchPitchers({ season, q, limit: 20 })}
        />
        <PlayerCombo
          label="Batter"
          value={batter}
          onChange={setBatter}
          fetchPlayers={(q) => searchBatters({ season, q, limit: 20 })}
        />

        <h3>Sample-size floors</h3>
        <div className="caption">
          Rows where the pitcher or batter are below these counts get filtered
          out. 0 shows everything, including noisy small samples.
        </div>

        <label>Min pitcher pitches (in this pitch+count)</label>
        <input
          type="number"
          min={0}
          value={minPitcherN}
          onChange={(e) => setMinPitcherN(Number(e.target.value) || 0)}
        />
        <label>Min batter swings (on this pitch+count)</label>
        <input
          type="number"
          min={0}
          value={minBatterSwings}
          onChange={(e) => setMinBatterSwings(Number(e.target.value) || 0)}
        />
      </div>

      <div className="content">
        <h1>Matchup Edges</h1>
        <div className="caption">
          Pitcher propensity × batter vulnerability per (pitch, count). Sort
          by <code>Weighted</code> to find the single highest-leverage pitch in a matchup.
        </div>

        {error && <div className="error">{error}</div>}

        {pairing && (
          <>
            <h2 style={{ marginTop: 20 }}>
              {pairing.player_name ?? `id:${pairing.pitcher}`} vs{" "}
              {pairing.batter_name ?? `id:${pairing.batter}`} — {pairing.season}
            </h2>
            <div className="metrics">
              <Metric
                label="Best edge"
                value={
                  pairing.best_pitch_type
                    ? `${pairing.best_pitch_type} in ${pairing.best_balls}-${pairing.best_strikes}`
                    : "—"
                }
                help={`Weighted ${fmtWeighted(
                  pairing.best_edge_weighted
                )} · Lift ${fmtLiftPP(pairing.best_edge_lift)}`}
              />
              <Metric
                label="2nd edge"
                value={pairing.second_pitch_type ?? "—"}
                help={`Weighted ${fmtWeighted(pairing.second_edge_weighted)}`}
              />
              <Metric
                label="3rd edge"
                value={pairing.third_pitch_type ?? "—"}
                help={`Weighted ${fmtWeighted(pairing.third_edge_weighted)}`}
              />
              <Metric
                label="Edge cells"
                value={pairing.n_edge_cells}
                help="(pitch, count) buckets with data for both sides"
              />
              <Metric
                label="Pitcher pitches (matched)"
                value={
                  pairing.pitcher_pitches_in_matched_cells?.toLocaleString?.() ??
                  "—"
                }
              />
            </div>

            <h2>All edges in this matchup</h2>
            <div className="caption">
              Sorted by <code>Weighted</code>. Weighted = Pitcher% × Lift,
              scaled by 1000 for readability.
            </div>
            <EdgeTable rows={pairing.edges} />
          </>
        )}

        {!pairing && topEdges && (
          <>
            <h2 style={{ marginTop: 20 }}>
              Top league edges · {season}
              {pitcher && ` · ${pitcher.name}`}
              {batter && ` · ${batter.name}`}
            </h2>
            {lowerSampleFloor && (
              <div className="caption">{lowerSampleFloor}</div>
            )}
            <EdgeTable rows={topEdges} showPlayers={!(pitcher && batter)} />
          </>
        )}

        {loading && !pairing && !topEdges && (
          <div className="loading">Loading…</div>
        )}
      </div>
    </div>
  );
}
