import { useEffect, useMemo, useState } from "react";

const RENDER_CAP = 1000;

const COLS = [
  { key: "pitcher", label: "Pitcher" },
  { key: "team", label: "Team" },
  { key: "game_date", label: "Date" },
  { key: "velo", label: "Velo (mph)", round: 1 },
  { key: "vsep", label: "VSep (in)", round: 1 },
  { key: "pitch_type", label: "Pitch type" },
  { key: "p_throws", label: "P-hand" },
  { key: "stand", label: "B-stand" },
  { key: "same_hand", label: "Same hand" },
  { key: "in_zone", label: "In zone" },
  { key: "description", label: "Description" },
  { key: "swing", label: "Swing" },
  { key: "whiff", label: "Whiff" },
  { key: "called_strike", label: "Called strike" },
];

function fmt(v, round) {
  if (v == null) return "";
  if (typeof v === "number" && round != null) return v.toFixed(round);
  return v;
}

export default function PitchDetailTable({ rows, pitchTypeLabels }) {
  const [pitcher, setPitcher] = useState("All");
  const [team, setTeam] = useState("All");
  const [ptype, setPtype] = useState("All");
  const [matchup, setMatchup] = useState("All");

  const applyFilters = (
    base,
    { pitcher: p, team: t, ptype: pt, matchup: mu } = {}
  ) => {
    let out = base;
    if (p && p !== "All") out = out.filter((r) => r.pitcher === p);
    if (t && t !== "All") out = out.filter((r) => r.team === t);
    if (pt && pt !== "All") out = out.filter((r) => r.pitch_type === pt);
    if (mu && mu !== "All") {
      const [ph, bs] = mu.split("/");
      out = out.filter((r) => r.p_throws === ph && r.stand === bs);
    }
    return out;
  };

  const uniqueSorted = (arr, key) =>
    [...new Set(arr.map((r) => r[key]).filter((v) => v != null))].sort();

  const matchupsOf = (arr) =>
    [
      ...new Set(
        arr
          .filter((r) => r.p_throws && r.stand)
          .map((r) => `${r.p_throws}/${r.stand}`)
      ),
    ].sort();

  const pitcherOpts = useMemo(
    () => [
      "All",
      ...uniqueSorted(
        applyFilters(rows, { team, ptype, matchup }),
        "pitcher"
      ),
    ],
    [rows, team, ptype, matchup]
  );
  const teamOpts = useMemo(
    () => [
      "All",
      ...uniqueSorted(
        applyFilters(rows, { pitcher, ptype, matchup }),
        "team"
      ),
    ],
    [rows, pitcher, ptype, matchup]
  );
  const ptypeOpts = useMemo(
    () => [
      "All",
      ...uniqueSorted(
        applyFilters(rows, { pitcher, team, matchup }),
        "pitch_type"
      ),
    ],
    [rows, pitcher, team, matchup]
  );
  const matchupOpts = useMemo(
    () => [
      "All",
      ...matchupsOf(applyFilters(rows, { pitcher, team, ptype })),
    ],
    [rows, pitcher, team, ptype]
  );

  useEffect(() => {
    if (!pitcherOpts.includes(pitcher)) setPitcher("All");
  }, [pitcherOpts, pitcher]);
  useEffect(() => {
    if (!teamOpts.includes(team)) setTeam("All");
  }, [teamOpts, team]);
  useEffect(() => {
    if (!ptypeOpts.includes(ptype)) setPtype("All");
  }, [ptypeOpts, ptype]);
  useEffect(() => {
    if (!matchupOpts.includes(matchup)) setMatchup("All");
  }, [matchupOpts, matchup]);

  const filtered = useMemo(() => {
    const out = applyFilters(rows, { pitcher, team, ptype, matchup });
    return [...out].sort((a, b) => {
      const pa = a.pitcher || "";
      const pb = b.pitcher || "";
      if (pa !== pb) return pa < pb ? -1 : 1;
      return (a.game_date || "") < (b.game_date || "") ? -1 : 1;
    });
  }, [rows, pitcher, team, ptype, matchup]);

  const presentTypes = useMemo(() => uniqueSorted(rows, "pitch_type"), [rows]);

  if (rows.length === 0) {
    return <div className="info">No pitches match the current filter.</div>;
  }

  return (
    <>
      <div className="filter-row">
        <div>
          <label>Team</label>
          <select value={team} onChange={(e) => setTeam(e.target.value)}>
            {teamOpts.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label>Pitcher</label>
          <select
            value={pitcher}
            onChange={(e) => setPitcher(e.target.value)}
          >
            {pitcherOpts.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label>Pitch type</label>
          <select value={ptype} onChange={(e) => setPtype(e.target.value)}>
            {ptypeOpts.map((o) => (
              <option key={o} value={o}>
                {o === "All" ? "All" : `${o} — ${pitchTypeLabels[o] || o}`}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label>Handedness matchup (P/B)</label>
          <select
            value={matchup}
            onChange={(e) => setMatchup(e.target.value)}
          >
            {matchupOpts.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </div>
      </div>
      {presentTypes.length > 0 && (
        <div className="caption">
          Pitch type key —{" "}
          {presentTypes
            .map((c) => `${c} = ${pitchTypeLabels[c] || c}`)
            .join(" · ")}
        </div>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, RENDER_CAP).map((r, i) => (
              <tr key={i}>
                {COLS.map((c) => (
                  <td key={c.key}>{fmt(r[c.key], c.round)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="caption">
        {filtered.length > RENDER_CAP
          ? `Showing first ${RENDER_CAP.toLocaleString()} of ${filtered.length.toLocaleString()} pitch rows. Filter to narrow down.`
          : `${filtered.length.toLocaleString()} pitch rows.`}
      </div>
    </>
  );
}
