import { Link, NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home.jsx";
import FirstPitchOffspeed from "./pages/FirstPitchOffspeed.jsx";
import Sequences from "./pages/Sequences.jsx";
import Matchup from "./pages/Matchup.jsx";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          MLB Pitch Analytics
        </Link>
        <nav className="topnav">
          <NavLink to="/tools/sequences">Sequences</NavLink>
          <NavLink to="/tools/matchup">Matchup edges</NavLink>
        </nav>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/tools/sequences" element={<Sequences />} />
          <Route path="/tools/matchup" element={<Matchup />} />
          <Route
            path="/reports/first-pitch-offspeed"
            element={<FirstPitchOffspeed />}
          />
        </Routes>
      </main>
    </div>
  );
}
