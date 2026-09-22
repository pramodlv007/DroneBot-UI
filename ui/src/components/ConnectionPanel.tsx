import { useEffect, useState, useCallback } from "react";
import { api } from "@/services/api";
import type { RegisteredRobot } from "@/types/robot";
import { useRobotStore } from "@/stores/robotStore";
import { useMissionStore } from "@/stores/missionStore";
import { isActiveMission } from "@/utils/mission";
import RobotConnectionSettings from "./RobotConnectionSettings";

interface Props {
  onProceed: () => void;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={`dot ${ok ? "ok" : "unknown"}`}
      style={{ display: "inline-block", marginRight: 6, verticalAlign: "middle" }} />
  );
}

function ConnectingSpinner() {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--accent)" }}>
      <span className="connecting-ring" />Connecting…
    </span>
  );
}

function RawTelemetryBlock({ robotId }: { robotId: string }) {
  const state = useRobotStore((s) => s.robots[robotId]);
  if (!state) return <div style={{ color: "var(--text-2)", fontSize: 10, marginTop: 8, fontFamily: "var(--mono)" }}>No telemetry yet…</div>;

  const rows: [string, string][] = [
    ["Mode", state.mode ?? "—"],
    ["Health", state.health],
    ["Pose X/Y/Z", `${state.pose.x.toFixed(2)} / ${state.pose.y.toFixed(2)} / ${state.pose.z.toFixed(2)} m`],
    ["Roll / Pitch / Yaw", `${(state.pose.roll * 57.3).toFixed(1)}° / ${(state.pose.pitch * 57.3).toFixed(1)}° / ${(state.pose.yaw * 57.3).toFixed(1)}°`],
  ];
  if (state.gps) {
    rows.push(["GPS Fix", String(state.gps.fix)]);
    rows.push(["Lat / Lon", `${state.gps.latitude.toFixed(6)}, ${state.gps.longitude.toFixed(6)}`]);
    rows.push(["Altitude AGL", `${state.gps.altitude.toFixed(1)} m`]);
  }
  if (state.battery) {
    rows.push(["Battery", `${state.battery.percentage?.toFixed(0) ?? "—"}% / ${state.battery.voltage?.toFixed(2) ?? "—"} V`]);
  }
  if (state.velocity) {
    rows.push(["Lin X / Ang Z", `${state.velocity.linear_x.toFixed(2)} m/s / ${state.velocity.angular_z.toFixed(2)} r/s`]);
  }
  const latency = state.received_timestamp_ms - state.source_timestamp_ms;
  rows.push(["Latency", `${latency} ms`]);

  return (
    <div style={{
      marginTop: 10, background: "var(--bg-0)", border: "1px solid var(--border)",
      borderRadius: 6, padding: "8px 10px",
    }}>
      <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--ok)", marginBottom: 6 }}>
        Telemetry
      </div>
      {rows.map(([label, val]) => (
        <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0", borderBottom: "1px solid var(--bg-2)", fontSize: 10.5 }}>
          <span style={{ color: "var(--text-2)" }}>{label}</span>
          <span style={{ fontFamily: "var(--mono)", color: "var(--text-0)", fontWeight: 600 }}>{val}</span>
        </div>
      ))}
    </div>
  );
}

function RobotSetupCard({ robot, mode, onRefresh }: { robot: RegisteredRobot; mode: string; onRefresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const isUav = robot.robotType === "UAV";
  const liveState = useRobotStore((s) => s.robots[robot.robotId]);
  const hasData = !!liveState?.connected;

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      if (robot.connected) {
        await api.disconnectRobot(robot.robotId);
      } else {
        await api.connectRobot(robot.robotId);
      }
      await onRefresh();
    } catch (e: any) {
      setError(String(e).replace("Error: POST /api/robots/", "").replace("/connect -> ", ": "));
    } finally {
      setBusy(false);
    }
  }

  const connStr = robot.connection.connection ?? robot.connection.namespace ?? "—";

  return (
    <div className="robot-setup-card" style={{
      background: "var(--bg-2)", border: `1px solid ${robot.connected ? "rgba(60,232,128,0.3)" : "var(--border)"}`,
      borderTop: `3px solid ${isUav ? "var(--drone-color)" : "var(--bot-color)"}`,
      borderRadius: "var(--radius-lg)", padding: 18,
      flex: 1, minWidth: 0, width: "100%", maxWidth: 420,
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div style={{
          fontSize: 20, width: 36, height: 36, borderRadius: 10,
          background: isUav ? "var(--accent-dim)" : "rgba(168,85,247,0.15)",
          border: `1px solid ${isUav ? "rgba(94,174,255,0.25)" : "rgba(168,85,247,0.25)"}`,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          {isUav ? "A" : "G"}
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-0)" }}>{robot.displayName}</div>
          <div style={{ fontSize: 10, color: isUav ? "var(--drone-color)" : "var(--bot-color)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            {robot.protocol} · {robot.robotType}
          </div>
        </div>
        <div style={{ marginLeft: "auto" }}>
          <span style={{
            fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 5,
            background: robot.connected ? "var(--ok-dim)" : "var(--unknown-dim)",
            color: robot.connected ? "var(--ok)" : "var(--text-2)",
            border: `1px solid ${robot.connected ? "rgba(60,232,128,0.2)" : "transparent"}`,
          }}>
            {robot.connected ? (hasData ? "● LIVE" : "● WAIT") : "○ OFFLINE"}
          </span>
        </div>
      </div>

      {/* Connection string display */}
      {mode !== "SIMULATION" && <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 9.5, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 3 }}>
          {isUav ? "MAVLink Connection String" : "ROS2 Namespace"}
        </div>
        <div style={{
          fontFamily: "var(--mono)", fontSize: 11, background: "var(--bg-0)",
          border: "1px solid var(--border)", borderRadius: 5, padding: "5px 8px",
          color: "var(--accent-bright)", wordBreak: "break-all",
        }}>
          {connStr}
        </div>
        {robot.connection.baud && (
          <div style={{ fontSize: 10, color: "var(--text-2)", marginTop: 3, fontFamily: "var(--mono)" }}>
            Baud: {robot.connection.baud}
          </div>
        )}
      </div>

      }
      {/* Error */}
      {error && (
        <div style={{
          color: "var(--crit)", fontSize: 10.5, background: "var(--crit-dim)",
          border: "1px solid rgba(255,69,96,0.25)", borderRadius: 5,
          padding: "5px 8px", marginBottom: 8,
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Buttons */}
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button
          className={robot.connected ? "danger" : "primary"}
          disabled={busy || mode === "UNKNOWN"}
          onClick={toggle}
          style={{ flex: 1, fontSize: 12, padding: "8px" }}
        >
          {busy ? <ConnectingSpinner /> : robot.connected ? "Disconnect" : "Connect"}
        </button>
        <button
          disabled={robot.connected || busy}
          onClick={() => setEditing(!editing)}
          title={robot.connected ? "Disconnect first to reconfigure" : "Configure connection"}
          style={{ fontSize: 12 }}
        >
          {editing ? "Close" : "Configure"}
        </button>
      </div>

      {/* Inline config editor */}
      {editing && (
        <RobotConnectionSettings
          robot={robot}
          onSaved={() => { setEditing(false); void onRefresh(); }}
        />
      )}

      {/* Live telemetry readout */}
      {robot.connected && <details className="quiet-details"><summary>View telemetry</summary><RawTelemetryBlock robotId={robot.robotId} /></details>}
    </div>
  );
}

export default function ConnectionPanel({ onProceed }: Props) {
  const [robots, setRobots] = useState<RegisteredRobot[]>([]);
  const [mode, setMode] = useState("UNKNOWN");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const missionState = useMissionStore(s => s.mission.state);
  const emergencyActive = useMissionStore(s => s.emergencyActive);
  const [modeError, setModeError] = useState<string | null>(null);
  const [modeBusy, setModeBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [list, health] = await Promise.all([api.listRobots(), api.getHealth()]);
      setRobots(list);
      setMode(String(health.deploymentMode ?? "UNKNOWN"));
      setLoadError(null);
    } catch {
      setLoadError("Could not reach the gateway. Check the connection and try again.");
      setMode("UNKNOWN");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 2000);
    return () => clearInterval(iv);
  }, [refresh]);

  async function switchMode(next: string) {
    setModeBusy(true);
    setModeError(null);
    try {
      const res = await api.setDeploymentMode(next);
      setMode(res.deploymentMode);
      await refresh();
    } catch (e: any) {
      setModeError(String(e).replace("Error: PATCH /api/health/mode -> 400: ", "").replace("Error: PATCH /api/health/mode -> 409: ", ""));
    } finally {
      setModeBusy(false);
    }
  }

  const connectedCount = robots.filter((r) => r.connected).length;
  const modeLocked = modeBusy || mode === "UNKNOWN" || connectedCount > 0 || isActiveMission(missionState) || emergencyActive;

  return (
    <div className="connection-screen">
      {/* ── Title ── */}
      <div className="connection-screen-header">

        <h1>Connections</h1>
        <p>Choose a mode, connect your robots, then open mission control.</p>
      </div>

      {/* ── Deployment Mode Switcher ── */}
      <div style={{
        width: "100%", maxWidth: 720, background: "var(--bg-2)",
        border: `2px solid ${mode === "PHYSICAL" ? "rgba(60,232,128,0.4)" : "rgba(255,180,58,0.3)"}`,
        borderRadius: "var(--radius-lg)", padding: "14px 18px",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: mode === "PHYSICAL" ? "var(--ok)" : "var(--warn)", marginBottom: 2 }}>
              {mode === "PHYSICAL" ? "Physical · Real hardware" : mode === "SIMULATION" ? "Simulation · Practice without hardware" : mode === "TEST" ? "Test · Hardware adapters" : "Checking deployment mode…"}
            </div>
            <div style={{ fontSize: 10.5, color: "var(--text-2)" }}>
              {mode === "UNKNOWN" ? "Waiting for the gateway to report its current mode."
                : connectedCount > 0 || isActiveMission(missionState)
                ? "Stop any active mission and disconnect all robots before changing mode."
                : "Simulation uses generated telemetry. Physical connects to your configured robots."}
            </div>
            {modeError && <div style={{ color: "var(--crit)", fontSize: 10.5, marginTop: 4 }}>⚠ {modeError}</div>}
          </div>
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            <button
              className={mode === "SIMULATION" ? "primary" : ""}
              disabled={modeLocked || mode === "SIMULATION"}
              onClick={() => switchMode("SIMULATION")}
              style={{ fontSize: 11, padding: "7px 14px" }}
            >
              SIMULATION
            </button>
            <button
              className={mode === "PHYSICAL" ? "primary" : ""}
              style={{
                fontSize: 11, padding: "7px 14px",
                ...(mode === "PHYSICAL" ? {} : { borderColor: "rgba(60,232,128,0.4)", color: "var(--ok)", background: "var(--ok-dim)" }),
              }}
              disabled={modeLocked || mode === "PHYSICAL"}
              onClick={() => switchMode("PHYSICAL")}
            >
              {modeBusy ? "…" : "PHYSICAL"}
            </button>
          </div>
        </div>
      </div>

      {/* ── Robot Cards ── */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", justifyContent: "center", maxWidth: 860, width: "100%" }}>
        {loading ? <div className="empty-state" role="status">Loading your robots…</div> : loadError ? (
          <div className="empty-state" role="alert"><p>{loadError}</p><button onClick={refresh}>Try again</button></div>
        ) : robots.length === 0 ? (
          <div className="empty-state">No robots configured. Add your robot team before starting a mission.</div>
        ) : robots.map(r => <RobotSetupCard key={r.robotId} robot={r} mode={mode} onRefresh={refresh} />)}
      </div>

      {/* ── Connection instructions ── */}
      <details className="setup-help">
        <summary>Physical hardware setup instructions</summary>
        <div className="setup-instructions" style={{
          background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)",
          padding: "14px 18px", display: "grid", gap: 20,
        }}>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--drone-color)", marginBottom: 8 }}>
              Pixhawk / MAVLink
            </div>
            <ol style={{ paddingLeft: 16, fontSize: 11, color: "var(--text-1)", lineHeight: 2, margin: 0 }}>
              <li>Switch mode to <strong>PHYSICAL</strong> above.</li>
              <li>Connect Pixhawk USB telemetry to PC.</li>
              <li>Click <strong>Configure</strong> on Drone card.</li>
              <li>Set connection to <code style={{ color: "var(--accent)", fontFamily: "var(--mono)", fontSize: 10 }}>COM4</code> and baud to <code style={{ color: "var(--accent)", fontFamily: "var(--mono)", fontSize: 10 }}>57600</code>.</li>
              <li>Click <strong>SAVE</strong> → <strong>Connect</strong>.</li>
            </ol>
            <div style={{ marginTop: 8, fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-2)", background: "var(--bg-3)", borderRadius: 5, padding: "5px 8px" }}>
              Baud 57600: most telemetry radios<br />
              Baud 115200: USB direct<br />
              UDP: udp:0.0.0.0:14550 (Mission Planner forward)
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--bot-color)", marginBottom: 8 }}>
              TurtleBot / ROS2
            </div>
            <ol style={{ paddingLeft: 16, fontSize: 11, color: "var(--text-1)", lineHeight: 2, margin: 0 }}>
              <li>Switch mode to <strong>PHYSICAL</strong> above.</li>
              <li>Ensure PC and TurtleBot are on same Wi-Fi.</li>
              <li>Click <strong>Configure</strong> on TurtleBot card.</li>
              <li>Copy the <code style={{ fontFamily: "var(--mono)", fontSize: 10 }}>ros2 launch</code> command shown.</li>
              <li>SSH into TurtleBot → run the command.</li>
              <li>Click <strong>Connect</strong> — data streams in.</li>
            </ol>
          </div>
        </div>
      </details>

      {/* ── Proceed button ── */}
      <div style={{
        maxWidth: 720, width: "100%", display: "flex", alignItems: "center",
        justifyContent: "space-between", gap: 12, flexWrap: "wrap",
        background: "var(--bg-2)", border: "1px solid var(--border)",
        borderRadius: "var(--radius)", padding: "10px 16px",
        marginBottom: 24,
      }}>
        <div style={{ fontSize: 12, color: "var(--text-1)" }}>
          <StatusDot ok={!loadError && !loading && connectedCount > 0} />
          {loadError ? "Robot status unavailable · Gateway offline" : loading ? "Checking robot connections…" :
            `${connectedCount} of ${robots.length} robots connected · ${mode.toLowerCase()}`}
        </div>
        <button
          onClick={onProceed}
          className="primary"
          style={{ fontSize: 12, padding: "8px 20px" }}
        >
          {!loadError && connectedCount >= 2 ? "Launch Mission Control →" : "Open Mission View →"}
        </button>
      </div>
    </div>
  );
}
