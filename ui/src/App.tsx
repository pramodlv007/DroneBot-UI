import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { connectGatewaySocket } from "@/services/socket";
import MissionControlPage from "@/pages/MissionControlPage";
import ExperimentsPage from "@/pages/ExperimentsPage";
import ReplayPage from "@/pages/ReplayPage";
import { useMissionStore } from "@/stores/missionStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { api } from "@/services/api";

function ModeBadge() {
  const [mode, setMode] = useState("UNKNOWN");
  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const health = await api.getHealth();
        if (!cancelled) {
          setMode(String(health.deploymentMode ?? "UNKNOWN"));
          useMissionStore.getState().setEmergencyActive(health.emergency === true);
        }
      } catch { if (!cancelled) setMode("UNKNOWN"); }
    }
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);
  return <NavLink to="/?view=connections" className={`mode-badge ${mode}`} title="Manage deployment mode in connection setup">{mode === "UNKNOWN" ? "Mode unavailable" : mode.charAt(0) + mode.slice(1).toLowerCase()}</NavLink>;
}

function ConnectionNotice() {
  const status = useConnectionStore(s => s.wsStatus);
  if (status === "OPEN") return null;
  return <div className="connection-notice" role="status">
    <strong>{status === "CONNECTING" ? "Connecting to gateway…" : "Gateway connection lost"}</strong>
    <span>Live data may be out of date. Reconnecting automatically.</span>
  </div>;
}

export default function App() {
  useEffect(() => {
    const disconnect = connectGatewaySocket();
    return disconnect;
  }, []);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <div className="top-bar">
        <NavLink to="/?view=mission" className="brand-name">DroneBot</NavLink>

        {/* Center: nav */}
        <div className="top-bar-center">
          <nav className="nav-tabs" aria-label="Main navigation">
            <NavLink to="/?view=mission" end className={({ isActive }) => (isActive ? "active" : "")}>
              Mission
            </NavLink>
            <NavLink to="/experiments" className={({ isActive }) => (isActive ? "active" : "")}>
              Experiments
            </NavLink>
            <NavLink to="/replay" className={({ isActive }) => (isActive ? "active" : "")}>
              Replay
            </NavLink>
          </nav>
        </div>

        {/* Right: health + mode + clock */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ModeBadge />
        </div>
      </div>

      <ConnectionNotice />
      <main id="main-content" className="main-content" tabIndex={-1}>
      <Routes>
        <Route path="/" element={<MissionControlPage />} />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/replay" element={<ReplayPage />} />
      </Routes>
      </main>
    </div>
  );
}
