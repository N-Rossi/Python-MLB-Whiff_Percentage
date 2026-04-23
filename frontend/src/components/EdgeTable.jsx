/**
 * Table of matchup_edges rows. Used in both the single-pairing page and
 * the league-wide top-edges browser.
 *
 * When `showPlayers` is true (leaderboard mode), pitcher + batter names
 * are prepended as columns. In single-pairing mode they're redundant.
 */
function pct(x) {
  return x == null ? "—" : (x * 100).toFixed(1) + "%";
}
function pp(x) {
  return x == null ? "—" : (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "pp";
}

export default function EdgeTable({ rows, showPlayers = false }) {
  if (!rows || rows.length === 0) {
    return <div className="caption">No edges at the current sample-size floor.</div>;
  }

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {showPlayers && (
              <>
                <th>Pitcher</th>
                <th>Batter</th>
              </>
            )}
            <th>Pitch</th>
            <th>Count</th>
            <th title="How often the pitcher throws this pitch in this count">
              Pitcher%
            </th>
            <th title="Pitcher sample size">Pit n</th>
            <th title="Batter shrunk whiff rate on this pitch+count">Bat Whiff%</th>
            <th title="Batter swings at this pitch+count">Bat n</th>
            <th title="League average whiff rate at this pitch+count">League</th>
            <th title="Batter whiff rate minus league average">Lift</th>
            <th title="Pitcher% × Lift — the leverage metric. Higher = bigger edge.">
              Weighted
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {showPlayers && (
                <>
                  <td>{r.player_name ?? `id:${r.pitcher}`}</td>
                  <td>{r.batter_name ?? `id:${r.batter}`}</td>
                </>
              )}
              <td>{r.pitch_type}</td>
              <td>
                {r.balls}-{r.strikes}
              </td>
              <td>{pct(r.pitcher_pct_shrunk)}</td>
              <td>{r.pitcher_n}</td>
              <td>{pct(r.batter_whiff_shrunk)}</td>
              <td>{r.batter_swings}</td>
              <td>{pct(r.league_whiff_rate)}</td>
              <td className={liftClass(r.edge_lift)}>{pp(r.edge_lift)}</td>
              <td className="weighted-col">
                {r.edge_weighted == null
                  ? "—"
                  : (r.edge_weighted * 1000).toFixed(2)}
              </td>
            </tr>
          ))}
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
