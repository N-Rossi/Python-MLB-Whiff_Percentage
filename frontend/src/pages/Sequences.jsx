import { useEffect, useMemo, useRef, useState } from "react";
import PlayerCombo from "../components/PlayerCombo.jsx";
import SequenceTable from "../components/SequenceTable.jsx";
import {
  getBatterSequences,
  getPitcherSequences,
  getPitchTypes,
  getSeasons,
  getSequenceLeaderboard,
  searchBatters,
  searchPitchers,
} from "../api.js";

const PITCHER_SORTS = [
  { v: "whiff_rate_shrunk", label: "Whiff rate (shrunk)" },
  { v: "lift", label: "Whiff lift vs league" },
  { v: "put_away_rate_shrunk", label: "Put-away rate" },
  { v: "n_sequences", label: "Sample size" },
];

const BATTER_SORTS = [
  { v: "whiff_rate_shrunk", label: "Whiff rate (shrunk)" },
  { v: "lift", label: "Whiff lift vs league" },
  { v: "strikeout_rate_shrunk", label: "Strikeout rate" },
  { v: "n_sequences", label: "Sample size" },
];

export default function Sequences() {
  const [mode, setMode] = useState("pitcher"); // "pitcher" | "batter" | "leaderboard"
  const [seasons, setSeasons] = useState([]);
  const [pitchTypes, setPitchTypes] = useState([]);
  const [season, setSeason] = useState(null);
  const [bootError, setBootError] = useState(null);

  // Pitcher-view state
  const [pitcher, setPitcher] = useState(null);
  const [pBalls, setPBalls] = useState("");
  const [pStrikes, setPStrikes] = useState("");
  const [pPitch1, setPPitch1] = useState("");
  const [pPitch2, setPPitch2] = useState("");
  const [pMinN, setPMinN] = useState(10);
  const [pSort, setPSort] = useState("whiff_rate_shrunk");

  // Batter-view state
  const [batter, setBatter] = useState(null);
  const [bPitch1, setBPitch1] = useState("");
  const [bPitch2, setBPitch2] = useState("");
  const [bMinN, setBMinN] = useState(10);
  const [bSort, setBSort] = useState("whiff_rate_shrunk");

  // Leaderboard state
  const [lbRole, setLbRole] = useState("pitcher");
  const [lbPitch1, setLbPitch1] = useState("FF");
  const [lbPitch2, setLbPitch2] = useState("CH");
  const [lbBalls, setLbBalls] = useState("");
  const [lbStrikes, setLbStrikes] = useState("");
  const [lbMinN, setLbMinN] = useState(50);

  // Results
  const [rows, setRows] = useState([]);
  const [header, setHeader] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getSeasons(), getPitchTypes()])
      .then(([s, p]) => {
        setSeasons(s.seasons);
        setPitchTypes(p.pitch_types);
        setSeason(s.seasons[0]);
      })
      .catch((e) => setBootError(e.message));
  }, []);

  // Debounced fetch driver — refires when anything relevant changes.
  const debRef = useRef();
  useEffect(() => {
    if (!season) return;
    clearTimeout(debRef.current);
    debRef.current = setTimeout(() => runQuery(), 200);
    return () => clearTimeout(debRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    mode, season,
    pitcher, pBalls, pStrikes, pPitch1, pPitch2, pMinN, pSort,
    batter, bPitch1, bPitch2, bMinN, bSort,
    lbRole, lbPitch1, lbPitch2, lbBalls, lbStrikes, lbMinN,
  ]);

  function runQuery() {
    setError(null);
    if (mode === "pitcher" && !pitcher) {
      setRows([]);
      setHeader("Pick a pitcher in the sidebar.");
      return;
    }
    if (mode === "batter" && !batter) {
      setRows([]);
      setHeader("Pick a batter in the sidebar.");
      return;
    }
    setLoading(true);

    const finish = (rows, head) => {
      setRows(rows);
      setHeader(head);
      setLoading(false);
    };
    const fail = (e) => {
      setError(e.message);
      setRows([]);
      setHeader(null);
      setLoading(false);
    };

    if (mode === "pitcher") {
      getPitcherSequences(pitcher.id, {
        season,
        balls: pBalls,
        strikes: pStrikes,
        pitch1: pPitch1,
        pitch2: pPitch2,
        min_n: pMinN,
        sort: pSort,
        limit: 100,
      })
        .then((d) =>
          finish(d.rows, `${d.player_name ?? `id:${d.pitcher}`} — ${d.rows.length} sequences`)
        )
        .catch(fail);
    } else if (mode === "batter") {
      getBatterSequences(batter.id, {
        season,
        pitch1: bPitch1,
        pitch2: bPitch2,
        min_n: bMinN,
        sort: bSort,
        limit: 100,
      })
        .then((d) =>
          finish(d.rows, `${d.batter_name ?? `id:${d.batter}`} — ${d.rows.length} sequences`)
        )
        .catch(fail);
    } else {
      getSequenceLeaderboard({
        pitch1: lbPitch1,
        pitch2: lbPitch2,
        season,
        role: lbRole,
        balls: lbRole === "pitcher" ? lbBalls : "",
        strikes: lbRole === "pitcher" ? lbStrikes : "",
        min_n: lbMinN,
        limit: 50,
      })
        .then((d) =>
          finish(
            d.rows,
            `Top ${lbRole}s on ${lbPitch1}→${lbPitch2} (${season}) — ${d.rows.length} players`
          )
        )
        .catch(fail);
    }
  }

  if (bootError) {
    return (
      <div className="error">
        Failed to load API metadata: {bootError}
      </div>
    );
  }
  if (!season) return <div className="loading">Loading…</div>;

  const pitchOpts = pitchTypes;
  const sortOpts = mode === "pitcher" ? PITCHER_SORTS : BATTER_SORTS;
  const tableRole =
    mode === "pitcher"
      ? "pitcher"
      : mode === "batter"
      ? "batter"
      : lbRole === "pitcher"
      ? "leaderboard-pitcher"
      : "leaderboard-batter";

  return (
    <div className="layout">
      <div className="sidebar">
        <h3>View</h3>
        <div className="radio-row">
          {[
            ["pitcher", "Pitcher"],
            ["batter", "Batter"],
            ["leaderboard", "Leaderboard"],
          ].map(([v, l]) => (
            <button
              key={v}
              type="button"
              className={mode === v ? "active" : ""}
              onClick={() => setMode(v)}
            >
              {l}
            </button>
          ))}
        </div>

        <label>Season</label>
        <select value={season} onChange={(e) => setSeason(Number(e.target.value))}>
          {seasons.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        {mode === "pitcher" && (
          <>
            <PlayerCombo
              label="Pitcher"
              value={pitcher}
              onChange={setPitcher}
              fetchPlayers={(q) => searchPitchers({ season, q, limit: 20 })}
            />
            <PitchPair
              v1={pPitch1} onV1={setPPitch1}
              v2={pPitch2} onV2={setPPitch2}
              pitchTypes={pitchOpts}
            />
            <CountFilter
              balls={pBalls} onBalls={setPBalls}
              strikes={pStrikes} onStrikes={setPStrikes}
            />
          </>
        )}

        {mode === "batter" && (
          <>
            <PlayerCombo
              label="Batter"
              value={batter}
              onChange={setBatter}
              fetchPlayers={(q) => searchBatters({ season, q, limit: 20 })}
            />
            <PitchPair
              v1={bPitch1} onV1={setBPitch1}
              v2={bPitch2} onV2={setBPitch2}
              pitchTypes={pitchOpts}
            />
            <div className="caption" style={{ marginTop: 8 }}>
              Batter sequences are rolled up across counts (see SAMPLE_SIZES.md).
            </div>
          </>
        )}

        {mode === "leaderboard" && (
          <>
            <label>Role</label>
            <div className="radio-row">
              {[
                ["pitcher", "Pitchers"],
                ["batter", "Batters"],
              ].map(([v, l]) => (
                <button
                  key={v}
                  type="button"
                  className={lbRole === v ? "active" : ""}
                  onClick={() => setLbRole(v)}
                >
                  {l}
                </button>
              ))}
            </div>
            <PitchPair
              v1={lbPitch1} onV1={setLbPitch1}
              v2={lbPitch2} onV2={setLbPitch2}
              pitchTypes={pitchOpts}
              required
            />
            {lbRole === "pitcher" && (
              <CountFilter
                balls={lbBalls} onBalls={setLbBalls}
                strikes={lbStrikes} onStrikes={setLbStrikes}
              />
            )}
          </>
        )}

        <label>
          Min sample size
          <input
            type="number"
            min={0}
            value={
              mode === "pitcher" ? pMinN : mode === "batter" ? bMinN : lbMinN
            }
            onChange={(e) => {
              const v = Number(e.target.value) || 0;
              if (mode === "pitcher") setPMinN(v);
              else if (mode === "batter") setBMinN(v);
              else setLbMinN(v);
            }}
          />
        </label>

        {mode !== "leaderboard" && (
          <>
            <label>Sort by</label>
            <select
              value={mode === "pitcher" ? pSort : bSort}
              onChange={(e) =>
                mode === "pitcher" ? setPSort(e.target.value) : setBSort(e.target.value)
              }
            >
              {sortOpts.map((o) => (
                <option key={o.v} value={o.v}>
                  {o.label}
                </option>
              ))}
            </select>
          </>
        )}
      </div>

      <div className="content">
        <h1>Pitch-sequence Analyzer</h1>
        <div className="caption">
          Every 2-pitch combo from the derived sequence tables, with
          league-average comparison and empirical-Bayes shrinkage.
        </div>

        {error && <div className="error">{error}</div>}
        {header && !error && (
          <div className="caption" style={{ marginTop: 12 }}>
            {header}
            {loading && " · loading…"}
          </div>
        )}

        <div style={{ marginTop: 12 }}>
          <SequenceTable rows={rows} role={tableRole} />
        </div>
      </div>
    </div>
  );
}

function PitchPair({ v1, onV1, v2, onV2, pitchTypes, required = false }) {
  return (
    <>
      <label>Pitch 1 {required && <span className="req">*</span>}</label>
      <select value={v1} onChange={(e) => onV1(e.target.value)}>
        {!required && <option value="">(any)</option>}
        {pitchTypes.map((p) => (
          <option key={p.code} value={p.code}>
            {p.code} — {p.label}
          </option>
        ))}
      </select>
      <label>Pitch 2 {required && <span className="req">*</span>}</label>
      <select value={v2} onChange={(e) => onV2(e.target.value)}>
        {!required && <option value="">(any)</option>}
        {pitchTypes.map((p) => (
          <option key={p.code} value={p.code}>
            {p.code} — {p.label}
          </option>
        ))}
      </select>
    </>
  );
}

function CountFilter({ balls, onBalls, strikes, onStrikes }) {
  return (
    <div className="filter-row cols-2" style={{ margin: "8px 0" }}>
      <div>
        <label>Balls</label>
        <select value={balls} onChange={(e) => onBalls(e.target.value)}>
          <option value="">any</option>
          {[0, 1, 2, 3].map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label>Strikes</label>
        <select value={strikes} onChange={(e) => onStrikes(e.target.value)}>
          <option value="">any</option>
          {[0, 1, 2].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
