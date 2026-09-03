import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { connectGatewaySocket } from "@/services/socket";
import HealthPanel from "@/components/HealthPanel";
import MissionControlPage from "@/pages/MissionControlPage";
import ExperimentsPage from "@/pages/ExperimentsPage";
import ReplayPage from "@/pages/ReplayPage";
import { api } from "@/services/api";

// Drone SVG icon (inline, no dependency)
function DroneIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 10.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" fill="currentColor" />
      <path d="M8 4h2.5L12 6l1.5-2H16l-2.5 4h-3L8 4z" fill="currentColor" opacity="0.7" />
      <path d="M8 20h2.5L12 18l1.5 2H16l-2.5-4h-3L8 20z" fill="currentColor" opacity="0.7" />
      <path d="M4 8v2.5L6 12l-2 1.5V16l4-2.5v-3L4 8z" fill="currentColor" opacity="0.7" />
      <path d="M20 8v2.5L18 12l2 1.5V16l-4-2.5v-3L20 8z" fill="currentColor" opacity="0.7" />
    </svg>
  );
}

function ModeBadge() {
  const [mode, setMode] = useState<string>("PHYSICAL");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Poll every 3s so the badge always reflects backend reality
  useEffect(() => {
    async function fetch() {
      try {
        const h: any = await api.getHealth();
        setMode(h.deploymentMode ?? h.deployment_mode ?? "PHYSICAL");
      } catch { /* backend not ready yet */ }
    }
    fetch();
    const t = setInterval(fetch, 3000);
    return () => clearInterval(t);
  }, []);

  async function toggle() {
    const next = mode === "SIMULATION" ? "PHYSICAL" : "SIMULATION";
    setBusy(true);
    setErr(null);
    try {
      // Must disconnect all first — backend enforces this
      const robots = await api.listRobots();
      for (const r of robots.filter((r: any) => r.connected)) {
        await api.disconnectRobot(r.robotId);
      }
      const res = await api.setDeploymentMode(next);
      setMode(res.deploymentMode);
    } catch (e: any) {
      setErr("Mode switch failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
      <button
        className={`mode-badge ${mode}`}
        onClick={toggle}
        disabled={busy}
        title={mode === "PHYSICAL" ? "Click to switch to SIMULATION mode" : "Click to switch to PHYSICAL mode (real hardware)"}
        style={{ border: "1px solid" }}
      >
        {busy ? (
          <span className="connecting-ring" style={{ width: 8, height: 8 }} />
        ) : mode === "PHYSICAL" ? (
          <svg width="8" height="8" viewBox="0 0 8 8"><circle cx="4" cy="4" r="4" fill="currentColor" /></svg>
        ) : (
          <svg width="8" height="8" viewBox="0 0 8 8"><circle cx="4" cy="4" r="3" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
        )}
        {mode}
      </button>
      {err && <div style={{ fontSize: 9, color: "var(--crit)", marginTop: 1 }}>{err}</div>}
    </div>
  );
}

function SysClock() {
  const [time, setTime] = useState(() => new Date().toLocaleTimeString("en-US", { hour12: false }));
  useEffect(() => {
    const t = setInterval(() => setTime(new Date().toLocaleTimeString("en-US", { hour12: false })), 1000);
    return () => clearInterval(t);
  }, []);
  return <span className="sys-clock">{time}</span>;
}

export default function App() {
  useEffect(() => {
    const disconnect = connectGatewaySocket();
    return disconnect;
  }, []);

  return (
    <div className="app-shell">
      <div className="top-bar">
        {/* Brand */}
        <div className="brand">
          <div className="brand-icon">
            <DroneIcon size={16} />
          </div>
          <div>
            <div className="brand-name">DroneBot Command</div>
            <div className="brand-sub">Aerial · Ground · Real-Time</div>
          </div>
        </div>

        {/* Center: nav */}
        <div className="top-bar-center">
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
        </div>

        {/* Right: health + mode + clock */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <SysClock />
          <ModeBadge />
          <HealthPanel />
        </div>
      </div>

      <Routes>
        <Route path="/" element={<MissionControlPage />} />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/replay" element={<ReplayPage />} />
      </Routes>
    </div>
  );
}
