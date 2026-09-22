import type { RegisteredRobot } from "@/types/robot";
import { fmtNum, healthDotClass, robotLabel } from "@/utils/format";
import AttitudeIndicator from "./AttitudeIndicator";
import DeadReckoningControl from "./DeadReckoningControl";

interface Props {
  robot: RegisteredRobot;
  isLeader: boolean;
  isFollower: boolean;
}

/** GPS fix quality bar: 0-6 segments */
function GpsFixBar({ fix }: { fix: number }) {
  const segments = 6;
  return (
    <div className="gps-fix-bar" title={`GPS fix type: ${fix}`}>
      {Array.from({ length: segments }).map((_, i) => {
        const active = i < fix;
        const cls = active ? (fix >= 3 ? "active" : "partial") : "";
        return <div key={i} className={`gps-fix-segment ${cls}`} />;
      })}
    </div>
  );
}

/** Battery percentage bar with color coding */
function BatteryBar({ pct }: { pct: number | null }) {
  if (pct === null) return <span style={{ color: "var(--text-2)", fontFamily: "var(--mono)" }}>—</span>;
  const cls = pct > 50 ? "high" : pct > 20 ? "med" : "low";
  const color = pct > 50 ? "var(--ok)" : pct > 20 ? "var(--warn)" : "var(--crit)";
  return (
    <div className="battery-bar-wrap">
      <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color }}>{pct.toFixed(0)}%</span>
      <div className="battery-bar-track">
        <div className={`battery-bar-fill ${cls}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
    </div>
  );
}

function DroneIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none">
      <ellipse cx="18" cy="18" rx="5" ry="5" fill="currentColor" />
      <path d="M18 13V5M18 31v-8M13 18H5M31 18h-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
      <circle cx="18" cy="4" r="3.5" stroke="currentColor" strokeWidth="1.2" fill="none" />
      <circle cx="18" cy="32" r="3.5" stroke="currentColor" strokeWidth="1.2" fill="none" />
      <circle cx="4" cy="18" r="3.5" stroke="currentColor" strokeWidth="1.2" fill="none" />
      <circle cx="32" cy="18" r="3.5" stroke="currentColor" strokeWidth="1.2" fill="none" />
    </svg>
  );
}

function BotIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none">
      <rect x="8" y="12" width="20" height="14" rx="3" fill="currentColor" opacity="0.85" />
      <rect x="4" y="22" width="5" height="8" rx="2" fill="currentColor" opacity="0.6" />
      <rect x="27" y="22" width="5" height="8" rx="2" fill="currentColor" opacity="0.6" />
      <rect x="11" y="7" width="14" height="8" rx="2" fill="currentColor" opacity="0.5" />
      <circle cx="14" cy="15" r="2" fill="var(--bg-0)" />
      <circle cx="22" cy="15" r="2" fill="var(--bg-0)" />
    </svg>
  );
}

function RobotDetails({ robot, isLeader, isFollower }: Props) {
  const s = robot.state;
  const role = isLeader ? "LEADER" : isFollower ? "FOLLOWER" : null;
  const isUav = robot.robotType === "UAV";
  const health = s?.health ?? "UNKNOWN";
  const healthClass = robot.connected ? `health-${health}` : "disconnected";
  const latency = s ? (s.received_timestamp_ms - s.source_timestamp_ms) : null;

  return (
    <div className={`robot-card ${healthClass}`}>
      {/* Header */}
      <div className="robot-card-header">
        <div className="robot-card-title">
          <div className={`robot-icon ${isUav ? "uav" : "ugv"}`}
            style={{ color: isUav ? "var(--drone-color)" : "var(--bot-color)" }}>
            {isUav ? <DroneIcon size={18} /> : <BotIcon size={18} />}
          </div>
          <div>
            <div className="robot-name">{robotLabel(robot.robotId)}</div>
            <div className="robot-protocol-badge">{robot.protocol} · {robot.robotType}</div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
          <span className="status-pill" style={{ fontSize: 9.5, padding: "3px 8px" }}>
            <span className={`dot ${robot.connected ? healthDotClass(health) : "unknown"}`} />
            {robot.connected ? health : "OFFLINE"}
          </span>
          {robot.deadReckoning.active && (
            <span className="badge WARNING" style={{ fontSize: 8.5 }} title="Position is an estimate — no GPS fix, dead reckoning active">
              ⚠ DEAD RECKONING
            </span>
          )}
          {role && (
            <span className={`badge NORMAL`} style={{ fontSize: 9 }}>{role}</span>
          )}
        </div>
      </div>

      {/* Indoor/GPS-denied tracking — only shown for adapters that support it (UAVs) */}
      {isUav && robot.deadReckoning.supported && (
        <DeadReckoningControl robotId={robot.robotId} info={robot.deadReckoning} connected={robot.connected} />
      )}

      {/* Mode row */}
      {s?.mode && (
        <div style={{ marginBottom: 8 }}>
          <span className="flight-mode-chip">{s.mode}</span>
          {s.mode === "ARMED" || (s.metadata?.armed) ? (
            <span style={{ marginLeft: 6, fontSize: 9, color: "var(--warn)", fontWeight: 700, textTransform: "uppercase" }}>⚡ ARMED</span>
          ) : null}
        </div>
      )}

      {!s ? (
        <div style={{ color: "var(--text-2)", fontSize: 11, padding: "8px 0" }}>
          {robot.connected ? "Waiting for telemetry…" : "Not connected"}
        </div>
      ) : (
        <>
          {/* UAV-specific: attitude + GPS */}
          {isUav && (
            <div style={{ display: "flex", gap: 12, marginBottom: 10, alignItems: "flex-start" }}>
              <AttitudeIndicator
                roll={s.pose.roll}
                pitch={s.pose.pitch}
              />
              <div style={{ flex: 1 }}>
                <div className="telemetry-grid">
                  {s.gps && (
                    <>
                      <span className="label">Altitude</span>
                      <span className="value">{fmtNum(s.gps.altitude, 1, " m")}</span>
                      <span className="label">GPS Fix</span>
                      <span className="value"><GpsFixBar fix={s.gps.fix} /></span>
                      <span className="label">Lat / Lon</span>
                      <span className="value" style={{ fontSize: 10 }}>
                        {fmtNum(s.gps.latitude, 5)},<br />{fmtNum(s.gps.longitude, 5)}
                      </span>
                    </>
                  )}
                  <span className="label">Yaw</span>
                  <span className="value">{fmtNum((s.pose.yaw * 180) / Math.PI, 0, "°")}</span>
                </div>
              </div>
            </div>
          )}

          {/* UGV-specific: position + velocity */}
          {!isUav && (
            <div className="telemetry-grid" style={{ marginBottom: 8 }}>
              <span className="label">Position (x, y)</span>
              <span className="value">{fmtNum(s.pose.x)}, {fmtNum(s.pose.y)} m</span>

              {s.velocity && (
                <>
                  <span className="label">Linear vel</span>
                  <span className="value">{fmtNum(s.velocity.linear_x, 2, " m/s")}</span>
                  <span className="label">Angular vel</span>
                  <span className="value">{fmtNum(s.velocity.angular_z, 2, " rad/s")}</span>
                </>
              )}
              <span className="label">Yaw</span>
              <span className="value">{fmtNum((s.pose.yaw * 180) / Math.PI, 0, "°")}</span>
            </div>
          )}

          <div className="card-divider" />

          {/* Battery + Latency — always shown */}
          <div className="telemetry-grid">
            <span className="label">Battery</span>
            <span className="value"><BatteryBar pct={s.battery?.percentage ?? null} /></span>
            {s.battery?.voltage != null && (
              <>
                <span className="label">Voltage</span>
                <span className="value">{fmtNum(s.battery.voltage, 1, " V")}</span>
              </>
            )}
            <span className="label">Latency</span>
            <span className="value" style={{
              color: latency == null ? "var(--text-2)"
                : latency < 100 ? "var(--ok)"
                : latency < 300 ? "var(--warn)" : "var(--crit)"
            }}>
              {fmtNum(latency, 0, " ms")}
            </span>
          </div>
        </>
      )}
    </div>
  );
}


export default function RobotCard(props: Props) {
  const { robot, isLeader, isFollower } = props;
  const state = robot.connected ? robot.state : null;
  return <article className="robot-summary">
    <div className="robot-summary-heading"><h3>{robot.displayName || robotLabel(robot.robotId)}</h3>
      <span className={robot.connected ? "connected-label" : "muted-label"}>{robot.connected ? "Connected" : "Offline"}</span></div>
    <p className="robot-role">{isLeader ? "Leader" : isFollower ? "Follower" : "No role assigned"}</p>
    {state && <dl>
      <div><dt>Battery</dt><dd>{fmtNum(state.battery?.percentage, 0, "%")}</dd></div>
      <div><dt>{robot.robotType === "UAV" ? "Altitude" : "Speed"}</dt><dd>{robot.robotType === "UAV" ? fmtNum(state.pose.z, 1, " m") : fmtNum(state.velocity?.linear_x, 2, " m/s")}</dd></div>
    </dl>}
    {state && ["WARNING", "CRITICAL"].includes(state.health) && <p className="robot-warning">{state.health.toLowerCase()} health · Check telemetry</p>}
    {state?.metadata.armed === true && <p className="robot-warning">Armed</p>}
    {robot.deadReckoning.active && <p className="robot-warning">Position estimated · Dead reckoning</p>}
    <details className="quiet-details"><summary>Telemetry & settings</summary><RobotDetails {...props} /></details>
  </article>;
}
