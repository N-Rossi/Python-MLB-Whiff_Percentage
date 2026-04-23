import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  Database,
  GitCompareArrows,
  Sparkles,
} from "lucide-react";
import { Badge } from "../components/ui/badge.jsx";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card.jsx";
import { getReports } from "../api.js";

const TOOLS = [
  {
    id: "sequences",
    path: "/tools/sequences",
    title: "Pitch-sequence analyzer",
    blurb:
      "Every 2-pitch combo a pitcher throws — or a batter faces — shrunk to league baseline. Pick a player, slice by count, or find league leaders on any specific sequence.",
    icon: BarChart3,
  },
  {
    id: "matchup",
    path: "/tools/matchup",
    title: "Pitcher × batter matchups",
    blurb:
      "Pitcher tendency × batter vulnerability per pitch and count. Surface the single highest-leverage pitch in any matchup, from either side's perspective.",
    icon: GitCompareArrows,
  },
];

const QUICK_TRIES = [
  {
    label: "Skubal's FF → CH on 0-2",
    detail: "His ~2.5× league put-away edge",
    href: "/tools/sequences",
  },
  {
    label: "Juan Soto's worst sequences",
    detail: "Sort by Lift to find holes",
    href: "/tools/sequences",
  },
  {
    label: "Skubal vs Soto matchup card",
    detail: "CH in 1-2 is the leverage pitch",
    href: "/tools/matchup",
  },
];

export default function Home() {
  const [reports, setReports] = useState(null);

  useEffect(() => {
    getReports()
      .then((r) => setReports(r.reports))
      .catch(() => setReports([]));
  }, []);

  return (
    <div className="space-y-12">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-card via-card to-primary/5 p-8 md:p-12">
        <div className="absolute right-0 top-0 h-64 w-64 -translate-y-1/2 translate-x-1/2 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative max-w-2xl space-y-4">
          <Badge variant="default" className="gap-1">
            <Sparkles className="h-3 w-3" />
            Phase 1 live
          </Badge>
          <h1 className="text-4xl font-semibold tracking-tight md:text-5xl">
            Pitch sequencing & matchup edges,
            <span className="text-muted-foreground">
              {" "}backed by the full Statcast history.
            </span>
          </h1>
          <p className="text-lg text-muted-foreground">
            Interactive analyzers over 7.9M+ pitches, with empirical-Bayes
            shrinkage and league comparison on every rate. No noisy small
            samples dressed up as insight.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link
              to="/tools/sequences"
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Open sequence analyzer
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="/tools/matchup"
              className="inline-flex items-center gap-2 rounded-md border border-border bg-transparent px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
            >
              Browse matchups
            </Link>
          </div>
        </div>
      </section>

      {/* Tool cards */}
      <section className="space-y-4">
        <div className="flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-semibold">Tools</h2>
            <p className="text-sm text-muted-foreground">
              Interactive analyzers over the Phase 1 derived tables.
            </p>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {TOOLS.map((t) => (
            <Link key={t.id} to={t.path} className="group">
              <Card className="h-full transition-colors hover:border-primary/50 hover:bg-card/70">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <span className="grid h-10 w-10 place-items-center rounded-lg bg-primary/10 text-primary">
                      <t.icon className="h-5 w-5" />
                    </span>
                    <CardTitle className="text-base">{t.title}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <CardDescription>{t.blurb}</CardDescription>
                  <div className="inline-flex items-center gap-1 text-sm font-medium text-primary opacity-80 transition-opacity group-hover:opacity-100">
                    Open
                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      {/* Quick tries */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Quick tries</h2>
        <div className="grid gap-3 md:grid-cols-3">
          {QUICK_TRIES.map((q, i) => (
            <Link
              key={i}
              to={q.href}
              className="group rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-primary/40"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-medium">{q.label}</div>
                  <div className="text-xs text-muted-foreground">{q.detail}</div>
                </div>
                <ArrowRight className="mt-0.5 h-3.5 w-3.5 text-muted-foreground transition-all group-hover:translate-x-0.5 group-hover:text-primary" />
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* Archive reports */}
      {reports && reports.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold">Report archive</h2>
            <Badge variant="outline" className="gap-1 normal-case">
              <Database className="h-3 w-3" />
              legacy
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Standalone analyses that predate the main pipeline. Kept as-is for
            reference.
          </p>
          <div className="grid gap-3">
            {reports.map((r) => (
              <Link
                key={r.id}
                to={r.path}
                className="group rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/40"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="font-medium">{r.title}</div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {r.summary}
                    </div>
                  </div>
                  <ArrowRight className="mt-1 h-4 w-4 text-muted-foreground transition-all group-hover:translate-x-0.5 group-hover:text-primary" />
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
