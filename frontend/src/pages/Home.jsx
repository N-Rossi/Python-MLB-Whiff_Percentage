import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getReports } from "../api.js";

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
      <p className="caption">Pick a report below.</p>
      <hr />
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
