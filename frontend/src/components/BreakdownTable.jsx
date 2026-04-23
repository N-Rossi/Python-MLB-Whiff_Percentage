function fmtRate(val, denom) {
  if (!denom) return "n/a";
  return `${val}%`;
}

export default function BreakdownTable({ title, rows }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Pitchers</th>
              <th>Pitches</th>
              <th>Swings</th>
              <th>Whiffs</th>
              <th>Whiff %</th>
              <th>Called</th>
              <th>CSW %</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} style={{ color: "#8b949e" }}>
                  (no data)
                </td>
              </tr>
            )}
            {rows.map((r) => {
              const s = r.stats;
              return (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td>{r.n_pitchers}</td>
                  <td>{s.pitches}</td>
                  <td>{s.swings}</td>
                  <td>{s.whiffs}</td>
                  <td>{fmtRate(s.whiff_rate, s.swings)}</td>
                  <td>{s.called_strikes}</td>
                  <td>{fmtRate(s.csw_rate, s.pitches)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
