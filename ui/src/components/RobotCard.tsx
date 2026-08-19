import type { RegisteredRobot } from "@/types/robot";
import { fmtNum, healthDotClass, robotLabel } from "@/utils/format";

interface Props {
  robot: RegisteredRobot;
  isLeader: boolean;
  isFollower: boolean;
}

export default function RobotCard({ robot, isLeader, isFollower }: Props) {
  const s = robot.state;
  const role = isLeader ? "LEADER" : isFollower ? "FOLLOWER" : null;

  return (
    <div className="robot-card">
      <div className="robot-card-header">
        <span className="name">{robotLabel(robot.robotId)}</span>
        <span className="status-pill">
          <span className={`dot ${robot.connected ? healthDotClass(s?.health) : "unknown"}`} />
          {robot.connected ? s?.health ?? "CONNECTED" : "DISCONNECTED"}
        </span>
      </div>

      {role && (
        <div style={{ marginBottom: 8 }}>
          <span className="badge NORMAL">{role}</span>
          <span style={{ marginLeft: 6, color: "var(--text-2)", fontSize: 11 }}>
            {robot.protocol} · {robot.robotType}
          </span>
        </div>
      )}
      {!role && (
        <div style={{ marginBottom: 8, color: "var(--text-2)", fontSize: 11 }}>
          {robot.protocol} · {robot.robotType}
        </div>
      )}

      {s ? (
        <div className="telemetry-grid">
          <span className="label">Mode</span>
          <span className="value">{s.mode ?? "—"}</span>

          <span className="label">Position (x, y)</span>
          <span className="value">
            {fmtNum(s.pose.x)}, {fmtNum(s.pose.y)}
          </span>

          {s.gps && (
            <>
              <span className="label">Altitude</span>
              <span className="value">{fmtNum(s.gps.altitude, 1, " m")}</span>
              <span className="label">GPS fix</span>
              <span className="value">{s.gps.fix}</span>
              <span className="label">Lat / Lon</span>
              <span className="value">
                {fmtNum(s.gps.latitude, 5)}, {fmtNum(s.gps.longitude, 5)}
              </span>
            </>
          )}

          <span className="label">Yaw</span>
          <span className="value">{fmtNum((s.pose.yaw * 180) / Math.PI, 0, "°")}</span>

          {s.velocity && (
            <>
              <span className="label">Linear vel</span>
              <span className="value">{fmtNum(s.velocity.linear_x, 2, " m/s")}</span>
              <span className="label">Angular vel</span>
              <span className="value">{fmtNum(s.velocity.angular_z, 2, " rad/s")}</span>
            </>
          )}

          {s.battery && (
            <>
              <span className="label">Battery</span>
              <span className="value">{fmtNum(s.battery.percentage, 0, "%")}</span>
            </>
          )}

          <span className="label">Latency</span>
          <span className="value">{fmtNum(s.received_timestamp_ms - s.source_timestamp_ms, 0, " ms")}</span>
        </div>
      ) : (
        <div style={{ color: "var(--text-2)", fontSize: 11 }}>No telemetry yet</div>
      )}
    </div>
  );
}
