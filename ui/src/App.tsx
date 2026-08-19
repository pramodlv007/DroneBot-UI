import { useEffect } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { connectGatewaySocket } from "@/services/socket";
import HealthPanel from "@/components/HealthPanel";
import MissionControlPage from "@/pages/MissionControlPage";
import ExperimentsPage from "@/pages/ExperimentsPage";
import ReplayPage from "@/pages/ReplayPage";

export default function App() {
  useEffect(() => {
    const disconnect = connectGatewaySocket();
    return disconnect;
  }, []);

  return (
    <div className="app-shell">
      <div className="top-bar">
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <h1>Heterogeneous Aerial-Ground Supervisory System</h1>
          <span className="subtitle">protocol-agnostic UAV/UGV coordination</span>
        </div>
        <nav className="nav-tabs">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
            Mission
          </NavLink>
          <NavLink to="/experiments" className={({ isActive }) => (isActive ? "active" : "")}>
            Experiments
          </NavLink>
          <NavLink to="/replay" className={({ isActive }) => (isActive ? "active" : "")}>
            Replay
          </NavLink>
        </nav>
        <HealthPanel />
      </div>

      <Routes>
        <Route path="/" element={<MissionControlPage />} />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/replay" element={<ReplayPage />} />
      </Routes>
    </div>
  );
}
