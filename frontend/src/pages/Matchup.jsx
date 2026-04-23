import { useEffect, useMemo, useRef, useState } from "react";
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
  const [perspective, setPerspective] = useState("pitcher"); // "pitcher" | "batter"

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
  //
  // `perspective` only triggers a refetch for the league-wide preview since
  // server-side sort depends on it. For the pairing view, sorting is
  // done client-side in a memo — no refetch needed when the toggle flips.
  const debRef = useRef();
  useEffect(() => {
    if (!season) return;
    clearTimeout(debRef.current);
    debRef.current = setTimeout(() => runQuery(), 200);
    return () => clearTimeout(debRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, pitcher, batter, minPitcherN, minBatterSwings, perspective]);

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
        perspective,
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

  // Client-side sort of pairing edges so the perspective toggle is instant —
  // no refetch, no network. DESC for pitcher (most leverage first), ASC for
  // batter (most-negative weighted first = where batter whiffs least vs
  // league, weighted by pitcher usage).
  const sortedPairingEdges = useMemo(() => {
    if (!pairing?.edges) return [];
    const arr = [...pairing.edges];
    arr.sort((a, b) => {
      const av = a.edge_weighted;
      const bv = b.edge_weighted;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return perspective === "batter" ? av - bv : bv - av;
    });
    return arr;
  }, [pairing, perspective]);

  const topThree = sortedPairingEdges.slice(0, 3);

  if (bootError) {
    return <div className="error">Failed to load API metadata: {bootError}</div>;
  }
  if (!season) return <div className="loading">Loading…</div>;

  const lowerSampleFloor = !pitcher || !batter
    ? "Default floors (pitcher_n≥50, batter_swings≥30) while browsing; drop them in sidebar for less-common pairs."
    : null;

  const perspectiveHint = perspective === "pitcher"
    ? "Sorted by highest leverage for the pitcher (edge_weighted DESC)."
    : "Sorted by batter's best spots — pitches thrown often where the batter whiffs LESS than league.";

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

        <label>Perspective</label>
        <div className="radio-row">
          {[
            ["pitcher", "Pitcher"],
            ["batter", "Batter"],
          ].map(([v, l]) => (
            <button
              key={v}
              type="button"
              className={perspective === v ? "active" : ""}
              onClick={() => setPerspective(v)}
            >
              {l}
            </button>
          ))}
        </div>
        <div className="caption" style={{ marginTop: 4 }}>
          Whose best edges are we looking for? Pitcher = highest leverage;
          Batter = spots with lowest whiff rate vs league.
        </div>

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
            <div className="caption">
              Perspective: <strong>{perspective}</strong>. {perspectiveHint}
            </div>
            <div className="metrics">
              <Metric
                label={
                  perspective === "pitcher" ? "Best edge (pitcher)" : "Best spot (batter)"
                }
                value={
                  topThree[0]
                    ? `${topThree[0].pitch_type} in ${topThree[0].balls}-${topThree[0].strikes}`
                    : "—"
                }
                help={
                  topThree[0]
                    ? `Weighted ${fmtWeighted(topThree[0].edge_weighted)} · Lift ${fmtLiftPP(topThree[0].edge_lift)}`
                    : ""
                }
              />
              <Metric
                label="2nd"
                value={
                  topThree[1]
                    ? `${topThree[1].pitch_type} in ${topThree[1].balls}-${topThree[1].strikes}`
                    : "—"
                }
                help={topThree[1] ? `Weighted ${fmtWeighted(topThree[1].edge_weighted)}` : ""}
              />
              <Metric
                label="3rd"
                value={
                  topThree[2]
                    ? `${topThree[2].pitch_type} in ${topThree[2].balls}-${topThree[2].strikes}`
                    : "—"
                }
                help={topThree[2] ? `Weighted ${fmtWeighted(topThree[2].edge_weighted)}` : ""}
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
              {perspectiveHint} Weighted = Pitcher% × Lift, scaled by 1000. Green
              cells = pitcher advantage; red = batter advantage (colors don't
              flip with perspective — they always show who wins the pitch).
            </div>
            <EdgeTable rows={sortedPairingEdges} />
          </>
        )}

        {!pairing && topEdges && (
          <>
            <h2 style={{ marginTop: 20 }}>
              Top league edges · {season} ·{" "}
              {perspective === "pitcher" ? "Pitcher perspective" : "Batter perspective"}
              {pitcher && ` · ${pitcher.name}`}
              {batter && ` · ${batter.name}`}
            </h2>
            <div className="caption">{perspectiveHint}</div>
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
