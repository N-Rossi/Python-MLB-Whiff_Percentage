import { NavLink, Route, Routes } from "react-router-dom";
import { BarChart3, GitCompareArrows, Zap } from "lucide-react";
import Home from "./pages/Home.jsx";
import FirstPitchOffspeed from "./pages/FirstPitchOffspeed.jsx";
import Sequences from "./pages/Sequences.jsx";
import Matchup from "./pages/Matchup.jsx";
import { cn } from "./lib/utils.js";

const NAV = [
  { to: "/tools/sequences", label: "Sequences", icon: BarChart3 },
  { to: "/tools/matchup", label: "Matchups", icon: GitCompareArrows },
];

export default function App() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-8 px-6">
          <NavLink
            to="/"
            className="flex items-center gap-2 font-semibold tracking-tight"
          >
            <span className="grid h-7 w-7 place-items-center rounded-md bg-primary/10 text-primary">
              <Zap className="h-4 w-4" />
            </span>
            <span>MLB Pitch Analytics</span>
          </NavLink>
          <nav className="flex items-center gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto text-xs text-muted-foreground">
            Phase 1 · Statcast 2015+
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/tools/sequences" element={<Sequences />} />
          <Route path="/tools/matchup" element={<Matchup />} />
          <Route path="/reports/first-pitch-offspeed" element={<FirstPitchOffspeed />} />
        </Routes>
      </main>
    </div>
  );
}
