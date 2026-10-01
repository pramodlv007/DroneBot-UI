import { useEffect, useState, useCallback } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { connectGatewaySocket } from "@/services/socket";
import HealthPanel from "@/components/HealthPanel";
import MissionControlPage from "@/pages/MissionControlPage";
import ExperimentsPage from "@/pages/ExperimentsPage";
import ReplayPage from "@/pages/ReplayPage";
import NotificationToast from "@/components/NotificationToast";
import AiMonitorPopup from "@/components/AiMonitorPopup";
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

/** Keyboard shortcut hints shown in top bar */
function ShortcutHints() {
  return (
    <div className="shortcut-hints" title="Keyboard shortcuts: Space=E-Stop, P=Pause, F=Fullscreen">
      <span className="shortcut-badge">⎵ E-STOP</span>
      <span className="shortcut-badge">P PAUSE</span>
      <span className="shortcut-badge">F FULL</span>
    </div>
  );
}

export default function App() {
  useEffect(() => {
    const disconnect = connectGatewaySocket();
    return disconnect;
  }, []);

  // ── Keyboard shortcuts (only when no input is focused) ──
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

    switch (e.key) {
      case " ": // Space → Emergency Stop
        e.preventDefault();
        api.emergencyStop().catch(() => {});
        break;
      case "p":
      case "P": // P → Pause/Resume
        api.togglePause().catch(() => {});
        break;
      case "f":
      case "F": // F → Fullscreen map
        {
          const mapEl = document.querySelector(".map-panel");
          if (mapEl) {
            if (document.fullscreenElement) {
              document.exitFullscreen().catch(() => {});
            } else {
              mapEl.requestFullscreen().catch(() => {});
            }
          }
        }
        break;
    }
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="app-shell">
      {/* Floating notification toasts — driven by backend events */}
      <NotificationToast />

      <div className="top-bar">
        {/* Brand */}
        <div className="brand">
          <div className="brand-icon" style={{
            width: 34, height: 34, borderRadius: 10,
            background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
            color: "#ffffff",
            border: "1px solid rgba(37,99,235,0.4)",
            boxShadow: "0 2px 8px rgba(37,99,235,0.25)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <DroneIcon size={18} />
          </div>
          <div>
            <div className="brand-name" style={{ fontSize: 14, letterSpacing: "0.06em" }}>DroneBot</div>
            <div className="brand-sub" style={{ fontSize: 9 }}>Command Center</div>
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

        {/* Right: shortcuts + health + mode + clock */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ShortcutHints />
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

      {/* Floating AI Monitor — reachable from any tab/page, not just the
          dedicated "AI Monitor" tab inside Mission Control. */}
      <AiMonitorPopup />
    </div>
  );
}

