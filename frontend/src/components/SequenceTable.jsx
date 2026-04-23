/**
 * Table of pitch-sequence rows. Drives both pitcher and batter views plus
 * the leaderboard, so the column set is configurable via `role`.
 *
 * role = "pitcher"  — columns include count slice, put-away rate
 * role = "batter"   — columns include strikeout rate, no count slice
 * role = "leaderboard-pitcher" — adds a Pitcher name column, drops player-identity
 * role = "leaderboard-batter"  — adds a Batter name column
 */
function pct(x) {
  return x == null ? "—" : (x * 100).toFixed(1) + "%";
}
function pp(x) {
  return x == null ? "—" : (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "pp";
}
function count(b, s) {
  if (b == null || s == null) return "—";
  return `${b}-${s}`;
}

export default function SequenceTable({ rows, role = "pitcher" }) {
  if (!rows || rows.length === 0) {
    return <div className="caption">No sequences match the current filters.</div>;
  }

  const isLeaderboard = role.startsWith("leaderboard");
  const isPitcher = role === "pitcher" || role === "leaderboard-pitcher";
  const isBatter = role === "batter" || role === "leaderboard-batter";

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {isLeaderboard && <th>{isPitcher ? "Pitcher" : "Batter"}</th>}
            {isPitcher && <th>Count</th>}
            <th>Pitch 1</th>
            <th>Pitch 2</th>
            <th title="Sequence sample size">n</th>
            <th>Swings</th>
            <th>Whiffs</th>
            <th title="Empirical-Bayes shrunk whiff rate">Whiff%</th>
            <th>League</th>
            <th title="Whiff rate minus league average, in percentage points">
              Lift
            </th>
            {isPitcher && !isLeaderboard && (
              <>
                <th title="Sequences where pitch 2 came with 2 strikes">2K chances</th>
                <th title="Strikeouts / 2-strike chances, shrunk">Put-away%</th>
              </>
            )}
            {isBatter && !isLeaderboard && (
              <>
                <th>2K chances</th>
                <th title="Strikeouts / 2-strike chances, shrunk">K rate</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const lift =
              r.whiff_rate_shrunk != null && r.league_whiff_rate != null
                ? r.whiff_rate_shrunk - r.league_whiff_rate
                : null;
            return (
              <tr key={i}>
                {isLeaderboard && <td>{r.name ?? `id:${r.id}`}</td>}
                {isPitcher && (
                  <td>{count(r.balls_before_p1, r.strikes_before_p1)}</td>
                )}
                <td>{r.pitch1_type}</td>
                <td>{r.pitch2_type}</td>
                <td>{r.n_sequences}</td>
                <td>{r.swings_on_p2 ?? "—"}</td>
                <td>{r.whiffs_on_p2 ?? "—"}</td>
                <td>{pct(r.whiff_rate_shrunk)}</td>
                <td>{pct(r.league_whiff_rate)}</td>
                <td className={liftClass(lift)}>{pp(lift)}</td>
                {isPitcher && !isLeaderboard && (
                  <>
                    <td>{r.two_strike_p2 ?? "—"}</td>
                    <td>{pct(r.put_away_rate_shrunk)}</td>
                  </>
                )}
                {isBatter && !isLeaderboard && (
                  <>
                    <td>{r.two_strike_p2 ?? "—"}</td>
                    <td>{pct(r.strikeout_rate_shrunk)}</td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function liftClass(lift) {
  if (lift == null) return "";
  if (lift > 0.03) return "lift-pos-strong";
  if (lift > 0) return "lift-pos";
  if (lift < -0.03) return "lift-neg-strong";
  if (lift < 0) return "lift-neg";
  return "";
}
