import { useMemo, useState } from "react";

const COLS = [
  { key: "name", label: "Pitcher" },
  { key: "team", label: "Team" },
  { key: "division", label: "Div" },
  { key: "fb_kind", label: "FB kind" },
  { key: "fb_velo", label: "FB velo (mph)", round: 1 },
  { key: "fb_ivb", label: "FB IVB (in)", round: 1 },
  { key: "fb_hbreak", label: "FB arm-side break (in)", round: 1 },
  { key: "fb_spin", label: "FB spin (rpm)", round: 0 },
  { key: "fb_extension", label: "FB extension (ft)", round: 2 },
  { key: "fb_usage_pct", label: "FB usage %", round: 1 },
  { key: "delta_v", label: "ΔV (mph)", round: 1 },
  { key: "vsep", label: "VSep (in)", round: 1 },
  { key: "hsep", label: "HSep (in)", round: 1 },
  { key: "release_sep", label: "Release sep (in)", round: 2 },
  { key: "fo_swings", label: "1P-OS swings" },
  { key: "whiff_rate", label: "1P-OS whiff %" },
];

function fmt(v, round) {
  if (v == null || (typeof v === "number" && Number.isNaN(v))) return "";
  if (typeof v === "number" && round != null) return v.toFixed(round);
  return v;
}

export default function TraitsTable({ rows }) {
  const [team, setTeam] = useState("All");
  const [fbKind, setFbKind] = useState("All");

  const teamOpts = useMemo(() => {
    const s = new Set(rows.map((r) => r.team).filter(Boolean));
    return ["All", ...[...s].sort()];
  }, [rows]);
  const kindOpts = useMemo(() => {
    const s = new Set(rows.map((r) => r.fb_kind).filter(Boolean));
    return ["All", ...[...s].sort()];
  }, [rows]);

  const filtered = useMemo(() => {
    let out = rows;
    if (team !== "All") out = out.filter((r) => r.team === team);
    if (fbKind !== "All") out = out.filter((r) => r.fb_kind === fbKind);
    return [...out].sort((a, b) => {
      const av = a.whiff_rate == null ? -Infinity : a.whiff_rate;
      const bv = b.whiff_rate == null ? -Infinity : b.whiff_rate;
      return bv - av;
    });
  }, [rows, team, fbKind]);

  if (rows.length === 0) {
    return (
      <div className="info">
        No eligible pitchers under the current velo floor / sample-size gates.
      </div>
    );
  }

  return (
    <>
      <div className="filter-row cols-2">
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
          <label>FB kind</label>
          <select value={fbKind} onChange={(e) => setFbKind(e.target.value)}>
            {kindOpts.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </div>
      </div>
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
            {filtered.map((r) => (
              <tr key={r.id}>
                {COLS.map((c) => (
                  <td key={c.key}>{fmt(r[c.key], c.round)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="caption">
        {filtered.length.toLocaleString()} pitchers shown.
        {team !== "All" || fbKind !== "All"
          ? ` Filtered to ${[
              team !== "All" ? `team ${team}` : null,
              fbKind !== "All" ? `FB kind ${fbKind}` : null,
            ]
              .filter(Boolean)
              .join(", ")}.`
          : ""}{" "}
        `FB kind` is each pitcher's primary fastball (FF or SI, whichever they
        throw more of). All FB movement / release traits are computed on that
        pitch only. ΔV = FB velo − OS velo. VSep/HSep = |FB − OS| induced
        break. Release sep = euclidean distance between avg FB and OS release
        points.
      </div>
    </>
  );
}
