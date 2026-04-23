import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getReports } from "../api.js";

const TOOLS = [
  {
    id: "sequences",
    path: "/tools/sequences",
    title: "Pitch-sequence analyzer",
    summary:
      "Every 2-pitch combo from a pitcher or batter's season, shrunk toward league average and compared to it. Three views: one pitcher's combos (count-sliced), one batter's combos, and a league-wide leaderboard for any specific sequence.",
  },
  {
    id: "matchup",
    path: "/tools/matchup",
    title: "Pitcher × batter matchup edges",
    summary:
      "Pitcher propensity × batter vulnerability per (pitch, count). Pick a pairing to see the single highest-leverage pitch plus the full table of edges sorted by the weighted leverage metric.",
  },
];

export default function Home() {
  const [reports, setReports] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getReports()
      .then((r) => setReports(r.reports))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <h1>MLB Pitch Analytics</h1>
      <p className="caption">
        Interactive analyzers over the Phase 1 data pipeline, plus a blog-style
        archive of standalone reports.
      </p>
      <hr />

      <h2>Tools</h2>
      {TOOLS.map((t) => (
        <div className="report-card" key={t.id}>
          <h3>{t.title}</h3>
          <div className="summary">{t.summary}</div>
          <Link to={t.path}>Open: {t.title} →</Link>
        </div>
      ))}

      <h2 style={{ marginTop: 24 }}>Reports</h2>
      {error && <div className="error">{error}</div>}
      {!reports && !error && <div className="loading">Loading…</div>}
      {reports &&
        reports.map((r) => (
          <div className="report-card" key={r.id}>
            <h3>{r.title}</h3>
            <div className="summary">{r.summary}</div>
            <Link to={r.path}>Open: {r.title} →</Link>
          </div>
        ))}
    </div>
  );
}
