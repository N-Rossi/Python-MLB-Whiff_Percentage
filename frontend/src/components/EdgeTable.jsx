import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table.jsx";
import { cn } from "../lib/utils.js";

function pct(x) {
  return x == null ? "—" : (x * 100).toFixed(1) + "%";
}
function pp(x) {
  return x == null ? "—" : (x >= 0 ? "+" : "") + (x * 100).toFixed(1);
}

function LiftCell({ lift }) {
  if (lift == null) return <span className="text-muted-foreground">—</span>;
  const strong = Math.abs(lift) > 0.03;
  if (lift > 0) {
    return (
      <span className={cn("inline-flex items-center gap-0.5 text-emerald-400", strong && "font-semibold")}>
        <ArrowUpRight className="h-3 w-3" />
        {pp(lift)}pp
      </span>
    );
  }
  if (lift < 0) {
    return (
      <span className={cn("inline-flex items-center gap-0.5 text-rose-400", strong && "font-semibold")}>
        <ArrowDownRight className="h-3 w-3" />
        {pp(lift)}pp
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 text-muted-foreground">
      <Minus className="h-3 w-3" /> 0.0pp
    </span>
  );
}

function PitchChip({ code }) {
  return (
    <span className="inline-flex h-6 items-center justify-center rounded border border-border bg-muted/30 px-1.5 font-mono text-xs font-medium">
      {code}
    </span>
  );
}

/** Matchup edges rows. Single-pairing view hides pitcher/batter columns since
 *  they're identical across every row. `showPlayers` flips them on for the
 *  league-wide top-edges browser. */
export default function EdgeTable({ rows, showPlayers = false }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 px-4 py-10 text-center text-sm text-muted-foreground">
        No edges at the current sample-size floor.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="max-h-[600px] overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {showPlayers && (
                <>
                  <TableHead>Pitcher</TableHead>
                  <TableHead>Batter</TableHead>
                </>
              )}
              <TableHead>Pitch</TableHead>
              <TableHead>Count</TableHead>
              <TableHead className="text-right" title="How often the pitcher throws this pitch in this count">
                Pit %
              </TableHead>
              <TableHead className="text-right">Pit n</TableHead>
              <TableHead className="text-right" title="Batter shrunk whiff rate on this pitch+count">
                Bat Whiff%
              </TableHead>
              <TableHead className="text-right">Bat n</TableHead>
              <TableHead className="text-right">League</TableHead>
              <TableHead className="text-right">Lift</TableHead>
              <TableHead className="text-right" title="Pitcher% × Lift — the leverage score (scaled ×1000).">
                Weighted
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={i}>
                {showPlayers && (
                  <>
                    <TableCell className="font-medium">
                      {r.player_name ?? <span className="text-muted-foreground">id:{r.pitcher}</span>}
                    </TableCell>
                    <TableCell className="font-medium">
                      {r.batter_name ?? <span className="text-muted-foreground">id:{r.batter}</span>}
                    </TableCell>
                  </>
                )}
                <TableCell><PitchChip code={r.pitch_type} /></TableCell>
                <TableCell className="font-mono text-muted-foreground">
                  {r.balls}-{r.strikes}
                </TableCell>
                <TableCell className="text-right">{pct(r.pitcher_pct_shrunk)}</TableCell>
                <TableCell className="text-right text-muted-foreground">{r.pitcher_n}</TableCell>
                <TableCell className="text-right">{pct(r.batter_whiff_shrunk)}</TableCell>
                <TableCell className="text-right text-muted-foreground">{r.batter_swings}</TableCell>
                <TableCell className="text-right text-muted-foreground">{pct(r.league_whiff_rate)}</TableCell>
                <TableCell className="text-right"><LiftCell lift={r.edge_lift} /></TableCell>
                <TableCell className="text-right font-semibold">
                  {r.edge_weighted == null ? "—" : (r.edge_weighted * 1000).toFixed(2)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
