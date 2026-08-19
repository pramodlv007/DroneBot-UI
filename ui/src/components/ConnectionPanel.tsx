import { useEffect, useState } from "react";
import { api } from "@/services/api";
import type { RegisteredRobot } from "@/types/robot";
import { robotLabel } from "@/utils/format";

interface Props {
  onAllConnected?: () => void;
}

export default function ConnectionPanel({ onAllConnected }: Props) {
  const [robots, setRobots] = useState<RegisteredRobot[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setRobots(await api.listRobots());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 2000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (robots.length > 0 && robots.every((r) => r.connected)) {
      onAllConnected?.();
    }
  }, [robots, onAllConnected]);

  async function toggle(robot: RegisteredRobot) {
    setBusy(robot.robotId);
    setError(null);
    try {
      if (robot.connected) {
        await api.disconnectRobot(robot.robotId);
      } else {
        await api.connectRobot(robot.robotId);
      }
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="connection-screen">
      <div>
        <h1 style={{ margin: 0, fontSize: 20, letterSpacing: "0.02em" }}>Available Robots</h1>
        <p style={{ color: "var(--text-2)", fontSize: 12, marginTop: 4 }}>
          Connect each robot independently. The mission view unlocks once at least two are connected.
        </p>
      </div>

      {error && <div style={{ color: "var(--crit)", fontSize: 12 }}>{error}</div>}

      <div className="connection-cards">
        {robots.map((robot) => (
          <div key={robot.robotId} className="connection-card">
            <div className="robot-type">
              {robot.protocol} · {robot.robotType}
            </div>
            <div className="robot-name">{robotLabel(robot.robotId)}</div>
            <div className="robot-detail">
              {robot.connected
                ? `Telemetry: ${robot.state ? "live" : "waiting..."}`
                : "Not connected"}
            </div>
            <button
              className={robot.connected ? "" : "primary"}
              disabled={busy === robot.robotId}
              onClick={() => toggle(robot)}
            >
              {busy === robot.robotId ? "..." : robot.connected ? "DISCONNECT" : "CONNECT"}
            </button>
            {robot.connected && (
              <div style={{ marginTop: 10, color: "var(--ok)", fontSize: 11 }}>
                ✓ Connected — {robot.capabilities.length} capabilities
              </div>
            )}
          </div>
        ))}
        {robots.length === 0 && <div className="empty-state">No robots configured in config/robots.yaml</div>}
      </div>
    </div>
  );
}
