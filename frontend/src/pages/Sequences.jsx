import { useEffect, useRef, useState } from "react";
import { BarChart3, Loader2, Target, Trophy, User, UsersRound } from "lucide-react";
import PlayerCombo from "../components/PlayerCombo.jsx";
import SequenceTable from "../components/SequenceTable.jsx";
import { Badge } from "../components/ui/badge.jsx";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card.jsx";
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
  getBatterSequences,
  getPitcherSequences,
  getPitchTypes,
  getSeasons,
  getSequenceLeaderboard,
  searchBatters,
  searchPitchers,
} from "../api.js";

const PITCHER_SORTS = [
  { v: "whiff_rate_shrunk", label: "Whiff rate (shrunk)" },
  { v: "lift", label: "Whiff lift vs league" },
  { v: "put_away_rate_shrunk", label: "Put-away rate" },
  { v: "n_sequences", label: "Sample size" },
];
const BATTER_SORTS = [
  { v: "whiff_rate_shrunk", label: "Whiff rate (shrunk)" },
  { v: "lift", label: "Whiff lift vs league" },
  { v: "strikeout_rate_shrunk", label: "Strikeout rate" },
  { v: "n_sequences", label: "Sample size" },
];
const ANY = "__any__"; // sentinel since Radix Select disallows "" values

export default function Sequences() {
  const [mode, setMode] = useState("pitcher");
  const [seasons, setSeasons] = useState([]);
  const [pitchTypes, setPitchTypes] = useState([]);
  const [season, setSeason] = useState(null);
  const [bootError, setBootError] = useState(null);

  // Pitcher-view
  const [pitcher, setPitcher] = useState(null);
  const [pBalls, setPBalls] = useState(ANY);
  const [pStrikes, setPStrikes] = useState(ANY);
  const [pPitch1, setPPitch1] = useState(ANY);
  const [pPitch2, setPPitch2] = useState(ANY);
  const [pMinN, setPMinN] = useState(10);
  const [pSort, setPSort] = useState("whiff_rate_shrunk");

  // Batter-view
  const [batter, setBatter] = useState(null);
  const [bPitch1, setBPitch1] = useState(ANY);
  const [bPitch2, setBPitch2] = useState(ANY);
  const [bMinN, setBMinN] = useState(10);
  const [bSort, setBSort] = useState("whiff_rate_shrunk");

  // Leaderboard
  const [lbRole, setLbRole] = useState("pitcher");
  const [lbPitch1, setLbPitch1] = useState("FF");
  const [lbPitch2, setLbPitch2] = useState("CH");
  const [lbBalls, setLbBalls] = useState(ANY);
  const [lbStrikes, setLbStrikes] = useState(ANY);
  const [lbMinN, setLbMinN] = useState(50);

  const [rows, setRows] = useState([]);
  const [header, setHeader] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getSeasons(), getPitchTypes()])
      .then(([s, p]) => {
        setSeasons(s.seasons);
        setPitchTypes(p.pitch_types);
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
  }, [
    mode, season,
    pitcher, pBalls, pStrikes, pPitch1, pPitch2, pMinN, pSort,
    batter, bPitch1, bPitch2, bMinN, bSort,
    lbRole, lbPitch1, lbPitch2, lbBalls, lbStrikes, lbMinN,
  ]);

  function runQuery() {
    setError(null);
    const clean = (v) => (v === ANY ? "" : v);

    if (mode === "pitcher" && !pitcher) {
      setRows([]); setHeader("Pick a pitcher in the sidebar.");
      return;
    }
    if (mode === "batter" && !batter) {
      setRows([]); setHeader("Pick a batter in the sidebar.");
      return;
    }
    setLoading(true);

    const finish = (rows, head) => {
      setRows(rows); setHeader(head); setLoading(false);
    };
    const fail = (e) => {
      setError(e.message); setRows([]); setHeader(null); setLoading(false);
    };

    if (mode === "pitcher") {
      getPitcherSequences(pitcher.id, {
        season, balls: clean(pBalls), strikes: clean(pStrikes),
        pitch1: clean(pPitch1), pitch2: clean(pPitch2),
        min_n: pMinN, sort: pSort, limit: 100,
      })
        .then((d) => finish(d.rows, `${d.player_name ?? `id:${d.pitcher}`} — ${d.rows.length} sequences`))
        .catch(fail);
    } else if (mode === "batter") {
      getBatterSequences(batter.id, {
        season, pitch1: clean(bPitch1), pitch2: clean(bPitch2),
        min_n: bMinN, sort: bSort, limit: 100,
      })
        .then((d) => finish(d.rows, `${d.batter_name ?? `id:${d.batter}`} — ${d.rows.length} sequences`))
        .catch(fail);
    } else {
      getSequenceLeaderboard({
        pitch1: lbPitch1, pitch2: lbPitch2, season, role: lbRole,
        balls: lbRole === "pitcher" ? clean(lbBalls) : "",
        strikes: lbRole === "pitcher" ? clean(lbStrikes) : "",
        min_n: lbMinN, limit: 50,
      })
        .then((d) => finish(d.rows, `Top ${lbRole}s on ${lbPitch1} → ${lbPitch2} · ${d.rows.length} players`))
        .catch(fail);
    }
  }

  if (bootError) {
    return <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-destructive">Failed to load API metadata: {bootError}</div>;
  }
  if (!season) {
    return <div className="py-24 text-center text-muted-foreground">Loading…</div>;
  }

  const sortOpts = mode === "pitcher" ? PITCHER_SORTS : BATTER_SORTS;
  const tableRole =
    mode === "pitcher" ? "pitcher"
      : mode === "batter" ? "batter"
      : lbRole === "pitcher" ? "leaderboard-pitcher" : "leaderboard-batter";
  const currentMinN = mode === "pitcher" ? pMinN : mode === "batter" ? bMinN : lbMinN;
  const setMinN = (v) => {
    if (mode === "pitcher") setPMinN(v);
    else if (mode === "batter") setBMinN(v);
    else setLbMinN(v);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BarChart3}
        title="Pitch-sequence analyzer"
        description="Every 2-pitch combo from the derived sequence tables, with league comparison and empirical-Bayes shrinkage."
      />

      <Tabs value={mode} onValueChange={setMode}>
        <TabsList>
          <TabsTrigger value="pitcher" className="gap-1.5">
            <User className="h-3.5 w-3.5" />
            Pitcher view
          </TabsTrigger>
          <TabsTrigger value="batter" className="gap-1.5">
            <Target className="h-3.5 w-3.5" />
            Batter view
          </TabsTrigger>
          <TabsTrigger value="leaderboard" className="gap-1.5">
            <Trophy className="h-3.5 w-3.5" />
            Leaderboard
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        {/* Sidebar */}
        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Filters</CardTitle>
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

              {mode === "pitcher" && (
                <>
                  <PlayerCombo
                    label="Pitcher"
                    value={pitcher}
                    onChange={setPitcher}
                    fetchPlayers={(q) => searchPitchers({ season, q, limit: 20 })}
                    placeholder="Pick a pitcher"
                  />
                  <PitchPair v1={pPitch1} onV1={setPPitch1} v2={pPitch2} onV2={setPPitch2} pitchTypes={pitchTypes} />
                  <CountRow balls={pBalls} setBalls={setPBalls} strikes={pStrikes} setStrikes={setPStrikes} />
                </>
              )}

              {mode === "batter" && (
                <>
                  <PlayerCombo
                    label="Batter"
                    value={batter}
                    onChange={setBatter}
                    fetchPlayers={(q) => searchBatters({ season, q, limit: 20 })}
                    placeholder="Pick a batter"
                  />
                  <PitchPair v1={bPitch1} onV1={setBPitch1} v2={bPitch2} onV2={setBPitch2} pitchTypes={pitchTypes} />
                  <p className="text-xs text-muted-foreground">
                    Batter sequences are rolled up across counts.
                  </p>
                </>
              )}

              {mode === "leaderboard" && (
                <>
                  <Field label="Role">
                    <Tabs value={lbRole} onValueChange={setLbRole}>
                      <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="pitcher">Pitchers</TabsTrigger>
                        <TabsTrigger value="batter">Batters</TabsTrigger>
                      </TabsList>
                    </Tabs>
                  </Field>
                  <PitchPair v1={lbPitch1} onV1={setLbPitch1} v2={lbPitch2} onV2={setLbPitch2} pitchTypes={pitchTypes} required />
                  {lbRole === "pitcher" && (
                    <CountRow balls={lbBalls} setBalls={setLbBalls} strikes={lbStrikes} setStrikes={setLbStrikes} />
                  )}
                </>
              )}

              <Field label="Min sample size">
                <Input
                  type="number" min={0}
                  value={currentMinN}
                  onChange={(e) => setMinN(Number(e.target.value) || 0)}
                />
              </Field>

              {mode !== "leaderboard" && (
                <Field label="Sort by">
                  <Select
                    value={mode === "pitcher" ? pSort : bSort}
                    onValueChange={(v) => (mode === "pitcher" ? setPSort(v) : setBSort(v))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {sortOpts.map((o) => <SelectItem key={o.v} value={o.v}>{o.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </Field>
              )}
            </CardContent>
          </Card>
        </aside>

        {/* Results */}
        <section className="min-w-0 space-y-4">
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              {error}
            </div>
          )}
          {header && !error && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>{header}</span>
              {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            </div>
          )}
          <SequenceTable rows={rows} role={tableRole} />
        </section>
      </div>
    </div>
  );
}

function PageHeader({ icon: Icon, title, description, right }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
      </div>
      {right}
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

function PitchPair({ v1, onV1, v2, onV2, pitchTypes, required = false }) {
  return (
    <>
      <Field label={`Pitch 1${required ? " *" : ""}`}>
        <PitchSelect value={v1} onChange={onV1} pitchTypes={pitchTypes} required={required} />
      </Field>
      <Field label={`Pitch 2${required ? " *" : ""}`}>
        <PitchSelect value={v2} onChange={onV2} pitchTypes={pitchTypes} required={required} />
      </Field>
    </>
  );
}

function PitchSelect({ value, onChange, pitchTypes, required }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger><SelectValue placeholder="Any" /></SelectTrigger>
      <SelectContent>
        {!required && <SelectItem value={ANY}>Any</SelectItem>}
        {pitchTypes.map((p) => (
          <SelectItem key={p.code} value={p.code}>
            <span className="font-mono">{p.code}</span>
            <span className="ml-2 text-muted-foreground">{p.label}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function CountRow({ balls, setBalls, strikes, setStrikes }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Balls">
        <Select value={balls} onValueChange={setBalls}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
            {[0, 1, 2, 3].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
          </SelectContent>
        </Select>
      </Field>
      <Field label="Strikes">
        <Select value={strikes} onValueChange={setStrikes}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
            {[0, 1, 2].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
          </SelectContent>
        </Select>
      </Field>
    </div>
  );
}
