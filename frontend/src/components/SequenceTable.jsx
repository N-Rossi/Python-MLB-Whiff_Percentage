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
function countStr(b, s) {
  if (b == null || s == null) return "—";
  return `${b}-${s}`;
}

function LiftCell({ lift }) {
  if (lift == null) {
    return <span className="text-muted-foreground">—</span>;
  }
  const abs = Math.abs(lift);
  const strong = abs > 0.03;
  if (lift > 0) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-0.5 text-emerald-400",
          strong && "font-semibold"
        )}
      >
        <ArrowUpRight className="h-3 w-3" />
        {pp(lift)}pp
      </span>
    );
  }
  if (lift < 0) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-0.5 text-rose-400",
          strong && "font-semibold"
        )}
      >
        <ArrowDownRight className="h-3 w-3" />
        {pp(lift)}pp
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 text-muted-foreground">
      <Minus className="h-3 w-3" />
      0.0pp
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

/**
 * Table of 2-pitch sequence rows, used in all three Sequences page modes.
 *   role = "pitcher"              — one pitcher, shows count slice + put-away rate
 *   role = "batter"               — one batter, shows K rate
 *   role = "leaderboard-pitcher"  — prepends Pitcher name column
 *   role = "leaderboard-batter"   — prepends Batter name column
 */
export default function SequenceTable({ rows, role = "pitcher" }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 px-4 py-10 text-center text-sm text-muted-foreground">
        No sequences match the current filters.
      </div>
    );
  }

  const isLeaderboard = role.startsWith("leaderboard");
  const isPitcher = role === "pitcher" || role === "leaderboard-pitcher";
  const isBatter = role === "batter" || role === "leaderboard-batter";

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="max-h-[600px] overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {isLeaderboard && <TableHead>{isPitcher ? "Pitcher" : "Batter"}</TableHead>}
              {isPitcher && <TableHead>Count</TableHead>}
              <TableHead>P1</TableHead>
              <TableHead>P2</TableHead>
              <TableHead className="text-right" title="Sequence sample size">n</TableHead>
              <TableHead className="text-right">Swings</TableHead>
              <TableHead className="text-right">Whiffs</TableHead>
              <TableHead className="text-right">Whiff%</TableHead>
              <TableHead className="text-right">League</TableHead>
              <TableHead className="text-right">Lift</TableHead>
              {isPitcher && !isLeaderboard && (
                <>
                  <TableHead className="text-right">2K</TableHead>
                  <TableHead className="text-right" title="Put-away % — strikeouts on 2-strike pitch 2">
                    Putaway%
                  </TableHead>
                </>
              )}
              {isBatter && !isLeaderboard && (
                <>
                  <TableHead className="text-right">2K</TableHead>
                  <TableHead className="text-right" title="Strikeouts / 2-strike chances">K%</TableHead>
                </>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r, i) => {
              const lift =
                r.whiff_rate_shrunk != null && r.league_whiff_rate != null
                  ? r.whiff_rate_shrunk - r.league_whiff_rate
                  : null;
              return (
                <TableRow key={i}>
                  {isLeaderboard && (
                    <TableCell className="font-medium">
                      {r.name ?? <span className="text-muted-foreground">id:{r.id}</span>}
                    </TableCell>
                  )}
                  {isPitcher && (
                    <TableCell className="font-mono text-muted-foreground">
                      {countStr(r.balls_before_p1, r.strikes_before_p1)}
                    </TableCell>
                  )}
                  <TableCell><PitchChip code={r.pitch1_type} /></TableCell>
                  <TableCell><PitchChip code={r.pitch2_type} /></TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {r.n_sequences}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {r.swings_on_p2 ?? "—"}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {r.whiffs_on_p2 ?? "—"}
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {pct(r.whiff_rate_shrunk)}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {pct(r.league_whiff_rate)}
                  </TableCell>
                  <TableCell className="text-right">
                    <LiftCell lift={lift} />
                  </TableCell>
                  {isPitcher && !isLeaderboard && (
                    <>
                      <TableCell className="text-right text-muted-foreground">
                        {r.two_strike_p2 ?? "—"}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {pct(r.put_away_rate_shrunk)}
                      </TableCell>
                    </>
                  )}
                  {isBatter && !isLeaderboard && (
                    <>
                      <TableCell className="text-right text-muted-foreground">
                        {r.two_strike_p2 ?? "—"}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {pct(r.strikeout_rate_shrunk)}
                      </TableCell>
                    </>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
