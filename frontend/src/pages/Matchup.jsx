import { useEffect, useMemo, useRef, useState } from "react";
import {
  GitCompareArrows,
  Loader2,
  Target,
  User,
  TrendingUp,
  TrendingDown,
  Hash,
  Zap,
} from "lucide-react";
import EdgeTable from "../components/EdgeTable.jsx";
import PlayerCombo from "../components/PlayerCombo.jsx";
import { Badge } from "../components/ui/badge.jsx";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../components/ui/card.jsx";
import { Input } from "../components/ui/input.jsx";
import { Label } from "../components/ui/label.jsx";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select.jsx";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs.jsx";
import {
  getMatchupPairing,
  getSeasons,
  getTopEdges,
  searchBatters,
  searchPitchers,
} from "../api.js";
import { cn } from "../lib/utils.js";

function fmtWeighted(x) {
  if (x == null) return "—";
  return (x * 1000).toFixed(2);
}
function fmtLiftPP(x) {
  if (x == null) return "—";
  return (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "pp";
}

export default function Matchup() {
  const [seasons, setSeasons] = useState([]);
  const [season, setSeason] = useState(null);
  const [pitcher, setPitcher] = useState(null);
  const [batter, setBatter] = useState(null);
  const [perspective, setPerspective] = useState("pitcher");

  const [minPitcherN, setMinPitcherN] = useState(0);
  const [minBatterSwings, setMinBatterSwings] = useState(0);

  const [pairing, setPairing] = useState(null);
  const [topEdges, setTopEdges] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [bootError, setBootError] = useState(null);

  useEffect(() => {
    getSeasons()
      .then((s) => {
        setSeasons(s.seasons);
        setSeason(s.seasons[0]);
      })
      .catch((e) => setBootError(e.message));
  }, []);

  const debRef = useRef();
  useEffect(() => {
    if (!season) return;
    clearTimeout(debRef.current);
    debRef.current = setTimeout(() => runQuery(), 200);
    return () => clearTimeout(debRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, pitcher, batter, minPitcherN, minBatterSwings, perspective]);

  function runQuery() {
    setError(null);
    setLoading(true);
    if (pitcher && batter) {
      setTopEdges(null);
      getMatchupPairing(pitcher.id, batter.id, {
        season,
        min_pitcher_n: minPitcherN,
        min_batter_swings: minBatterSwings,
      })
        .then(setPairing)
        .catch((e) => {
          setPairing(null);
          setError(e.message);
        })
        .finally(() => setLoading(false));
    } else {
      setPairing(null);
      getTopEdges({
        season,
        pitcher_id: pitcher?.id,
        batter_id: batter?.id,
        min_pitcher_n: Math.max(minPitcherN, 50),
        min_batter_swings: Math.max(minBatterSwings, 30),
        perspective,
        limit: 50,
      })
        .then((d) => setTopEdges(d.rows))
        .catch((e) => {
          setTopEdges(null);
          setError(e.message);
        })
        .finally(() => setLoading(false));
    }
  }

  const sortedEdges = useMemo(() => {
    if (!pairing?.edges) return [];
    const arr = [...pairing.edges];
    arr.sort((a, b) => {
      const av = a.edge_weighted;
      const bv = b.edge_weighted;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return perspective === "batter" ? av - bv : bv - av;
    });
    return arr;
  }, [pairing, perspective]);
  const topThree = sortedEdges.slice(0, 3);

  if (bootError) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-destructive">
        Failed to load API metadata: {bootError}
      </div>
    );
  }
  if (!season) {
    return <div className="py-24 text-center text-muted-foreground">Loading…</div>;
  }

  const perspectiveHint =
    perspective === "pitcher"
      ? "Sorted by the pitcher's highest-leverage pitches — where they throw often and the batter whiffs more than league."
      : "Sorted by the batter's best spots — pitches thrown often where the batter whiffs less than league.";

  return (
    <div className="space-y-6">
      <PageHeader
        icon={GitCompareArrows}
        title="Pitcher × batter matchups"
        description="Pitcher propensity × batter vulnerability per pitch and count. Find the single highest-leverage pitch in any matchup — from either perspective."
      />

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        {/* Sidebar */}
        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Matchup</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Season">
                <Select value={String(season)} onValueChange={(v) => setSeason(Number(v))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {seasons.map((s) => <SelectItem key={s} value={String(s)}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
              <PlayerCombo
                label="Pitcher"
                value={pitcher}
                onChange={setPitcher}
                fetchPlayers={(q) => searchPitchers({ season, q, limit: 20 })}
                placeholder="Pick a pitcher"
              />
              <PlayerCombo
                label="Batter"
                value={batter}
                onChange={setBatter}
                fetchPlayers={(q) => searchBatters({ season, q, limit: 20 })}
                placeholder="Pick a batter"
              />
              <Field label="Perspective">
                <Tabs value={perspective} onValueChange={setPerspective}>
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="pitcher" className="gap-1">
                      <User className="h-3 w-3" /> Pitcher
                    </TabsTrigger>
                    <TabsTrigger value="batter" className="gap-1">
                      <Target className="h-3 w-3" /> Batter
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </Field>
              <p className="text-xs text-muted-foreground">
                Whose best edges are we looking for? Pitcher = highest leverage;
                Batter = spots with lowest whiff rate vs league.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Sample-size floors</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Hide rows below these counts. 0 shows everything (including noisy
                small samples).
              </p>
              <Field label="Min pitcher pitches">
                <Input type="number" min={0} value={minPitcherN}
                  onChange={(e) => setMinPitcherN(Number(e.target.value) || 0)} />
              </Field>
              <Field label="Min batter swings">
                <Input type="number" min={0} value={minBatterSwings}
                  onChange={(e) => setMinBatterSwings(Number(e.target.value) || 0)} />
              </Field>
            </CardContent>
          </Card>
        </aside>

        {/* Content */}
        <section className="min-w-0 space-y-5">
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              {error}
            </div>
          )}

          {pairing && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-xl font-semibold tracking-tight">
                  {pairing.player_name ?? `id:${pairing.pitcher}`}
                  <span className="mx-2 text-muted-foreground">vs</span>
                  {pairing.batter_name ?? `id:${pairing.batter}`}
                  <Badge variant="outline" className="ml-3 font-mono">{pairing.season}</Badge>
                </h2>
                <Badge variant={perspective === "pitcher" ? "default" : "success"} className="gap-1">
                  {perspective === "pitcher" ? <User className="h-3 w-3" /> : <Target className="h-3 w-3" />}
                  {perspective} perspective
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">{perspectiveHint}</p>

              {topThree[0] && (
                <BestEdgeHero row={topThree[0]} perspective={perspective} />
              )}

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <MiniEdgeCard rank={2} row={topThree[1]} />
                <MiniEdgeCard rank={3} row={topThree[2]} />
                <StatTile icon={Hash} label="Edge cells"
                  value={pairing.n_edge_cells}
                  help="(pitch, count) buckets with data for both sides" />
                <StatTile icon={Zap} label="Pitcher pitches"
                  value={pairing.pitcher_pitches_in_matched_cells?.toLocaleString?.() ?? "—"}
                  help="summed across matched cells" />
              </div>

              <div className="pt-2 space-y-2">
                <h3 className="text-base font-semibold">All edges in this matchup</h3>
                <p className="text-xs text-muted-foreground">
                  Weighted = Pitcher% × Lift (×1000). Green = pitcher advantage;
                  red = batter advantage. Colors don't flip with perspective —
                  they always show who wins the pitch.
                </p>
                <EdgeTable rows={sortedEdges} />
              </div>
            </>
          )}

          {!pairing && topEdges && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-xl font-semibold">Top league edges · {season}</h2>
                  <p className="text-sm text-muted-foreground">
                    {perspectiveHint}
                    {(!pitcher || !batter) && " Pick a pitcher and a batter to see a full scouting card."}
                  </p>
                </div>
                <Badge variant={perspective === "pitcher" ? "default" : "success"} className="gap-1">
                  {perspective === "pitcher" ? <User className="h-3 w-3" /> : <Target className="h-3 w-3" />}
                  {perspective} perspective
                </Badge>
              </div>
              <EdgeTable rows={topEdges} showPlayers={!(pitcher && batter)} />
            </>
          )}

          {loading && !pairing && !topEdges && (
            <div className="flex items-center justify-center gap-2 py-24 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading…
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function BestEdgeHero({ row, perspective }) {
  const lift = row.edge_lift;
  const liftIcon = lift == null ? null : lift > 0 ? TrendingUp : TrendingDown;
  const liftClass = lift == null ? "text-muted-foreground"
    : lift > 0 ? "text-emerald-400" : "text-rose-400";
  const Icon = liftIcon;
  const headlineLabel = perspective === "pitcher" ? "Best edge for the pitcher" : "Best spot for the batter";

  return (
    <Card className="relative overflow-hidden border-primary/30 bg-gradient-to-br from-card to-primary/5">
      <div className="absolute right-0 top-0 h-40 w-40 -translate-y-1/3 translate-x-1/3 rounded-full bg-primary/10 blur-3xl" />
      <CardContent className="relative p-6">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="space-y-2">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              {headlineLabel}
            </div>
            <div className="flex items-center gap-3">
              <span className="inline-flex h-12 items-center justify-center rounded-lg border border-border bg-muted/40 px-3 font-mono text-2xl font-semibold">
                {row.pitch_type}
              </span>
              <div>
                <div className="text-3xl font-semibold tracking-tight">
                  {row.balls}-{row.strikes}
                </div>
                <div className="text-xs text-muted-foreground">count</div>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-6">
            <HeroMetric label="Weighted" value={fmtWeighted(row.edge_weighted)} />
            <HeroMetric
              label="Lift vs league"
              value={fmtLiftPP(lift)}
              valueClass={liftClass}
              icon={Icon}
            />
            <HeroMetric label="Pitch %" value={((row.pitcher_pct_shrunk ?? 0) * 100).toFixed(1) + "%"} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function HeroMetric({ label, value, valueClass, icon: Icon }) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn("flex items-center gap-1.5 text-2xl font-semibold tabular-nums tracking-tight", valueClass)}>
        {Icon && <Icon className="h-4 w-4" />}
        {value}
      </div>
    </div>
  );
}

function MiniEdgeCard({ rank, row }) {
  if (!row) {
    return (
      <Card className="opacity-50">
        <CardContent className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
            #{rank}
          </div>
          <div className="mt-1 text-lg font-semibold text-muted-foreground">—</div>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
          #{rank}
        </div>
        <div className="mt-1 flex items-center gap-2">
          <span className="inline-flex h-7 items-center justify-center rounded border border-border bg-muted/40 px-1.5 font-mono text-xs font-medium">
            {row.pitch_type}
          </span>
          <span className="font-mono text-sm text-muted-foreground">
            {row.balls}-{row.strikes}
          </span>
        </div>
        <div className="mt-2 text-lg font-semibold tabular-nums">
          {fmtWeighted(row.edge_weighted)}
        </div>
        <div className="text-[11px] text-muted-foreground">weighted</div>
      </CardContent>
    </Card>
  );
}

function StatTile({ icon: Icon, label, value, help }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
        </div>
        <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
        {help && <div className="text-[11px] text-muted-foreground">{help}</div>}
      </CardContent>
    </Card>
  );
}

function PageHeader({ icon: Icon, title, description }) {
  return (
    <div className="flex items-start gap-3">
      <span className="grid h-10 w-10 place-items-center rounded-lg bg-primary/10 text-primary">
        <Icon className="h-5 w-5" />
      </span>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
