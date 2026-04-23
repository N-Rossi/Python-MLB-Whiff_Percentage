import { Link, Route, Routes } from "react-router-dom";
import Home from "./pages/Home.jsx";
import FirstPitchOffspeed from "./pages/FirstPitchOffspeed.jsx";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          MLB Pitch Analytics
        </Link>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/reports/first-pitch-offspeed"
            element={<FirstPitchOffspeed />}
          />
        </Routes>
      </main>
    </div>
  );
}
