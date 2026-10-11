/**
 * LiveMetricsBar — compact horizontal strip showing live data from every
 * connected robot, plus common metrics (separation, latency). Sits between
 * the top-bar and the main grid in the Mission view so operators can always
 * glance at the most critical numbers without scrolling.
 */
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { fmtNum } from "@/utils/format";
import MissionHealthGauge from "./MissionHealthGauge";

function Metric({
  label, value, unit = "", color, title,
}: {
  label: string; value: string | number | null; unit?: string; color?: string; title?: string;
}) {
  const display = value === null || value === undefined ? "—" : `${value}${unit}`;
  return (
    <div className="lmb-metric" title={title}>
      <span className="lmb-label">{label}</span>
      <span className="lmb-value" style={{ color: color ?? "var(--text-0)" }}>{display}</span>
    </div>
  );
}

function Divider() {
  return <div style={{ width: 1, height: 28, background: "var(--border)", flexShrink: 0 }} />;
}

function BattColor(pct: number | null | undefined): string {
  if (pct == null) return "var(--text-2)";
  if (pct > 50) return "var(--ok)";
  if (pct > 20) return "var(--warn)";
  return "var(--crit)";
}

function LatColor(ms: number | null): string {
  if (ms == null) return "var(--text-2)";
  if (ms < 100) return "var(--ok)";
  if (ms < 300) return "var(--warn)";
  return "var(--crit)";
}

export default function LiveMetricsBar() {
  const robots = useRobotStore((s) => s.robots);
  const coord = useCoordinationStore((s) => s.coordination);

  // This bar's whole purpose is "live data from every connected robot" (see
  // header comment) — a disconnected robot's last-known frame must not
  // render here looking exactly like a live one, or the strip lies about
  // what's actually happening right now.
  const robotList = Object.values(robots).filter((r) => r.connected && !r.metadata?.awaiting_odom);
  const drone = robotList.find((r) => r.robot_type === "UAV");
  const bot = robotList.find((r) => r.robot_type === "UGV");

  // Any known UGV, live or not — used to keep the bot section visible with a
  // status badge instead of silently dropping it when it isn't streaming.
  const anyBot = Object.values(robots).find((r) => r.robot_type === "UGV");
  const botStatus = anyBot?.metadata?.awaiting_odom
    ? "AWAITING /ODOM"
    : anyBot && !anyBot.connected
    ? "OFFLINE"
    : "NOT CONNECTED";

  const droneLat = drone ? drone.received_timestamp_ms - drone.source_timestamp_ms : null;
  const botLat = bot ? bot.received_timestamp_ms - bot.source_timestamp_ms : null;

  if (robotList.length === 0) return null;

  return (
    <div className="live-metrics-bar">
      {/* ── DRONE section ── */}
      {drone && (
        <>
          <div className="lmb-section-label" style={{ color: "var(--drone-color)" }}>
            🚁 {drone.robot_id.replace(/_/g, " ").toUpperCase()}
          </div>

          <Metric
            label="MODE"
            value={drone.mode ?? "—"}
            color="var(--accent-bright)"
            title="Current flight mode"
          />
          <Metric
            label="ALT"
            value={drone.gps ? fmtNum(drone.gps.altitude, 1) : fmtNum(drone.pose.z, 1)}
            unit=" m"
            title="Altitude AGL (m)"
          />
          {drone.gps && (
            <Metric
              label="GPS"
              value={`${drone.gps.fix}/6`}
              color={drone.gps.fix >= 3 ? "var(--ok)" : drone.gps.fix >= 1 ? "var(--warn)" : "var(--crit)"}
              title={`GPS fix type ${drone.gps.fix}`}
            />
          )}
          <Metric
            label="ROLL"
            value={fmtNum((drone.pose.roll * 180) / Math.PI, 1)}
            unit="°"
            title="Roll angle"
          />
          <Metric
            label="PITCH"
            value={fmtNum((drone.pose.pitch * 180) / Math.PI, 1)}
            unit="°"
            title="Pitch angle"
          />
          <Metric
            label="YAW"
            value={fmtNum((drone.pose.yaw * 180) / Math.PI, 0)}
            unit="°"
            title="Yaw / heading"
          />
          <Metric
            label="BATT"
            value={fmtNum(drone.battery?.percentage, 0)}
            unit="%"
            color={BattColor(drone.battery?.percentage)}
            title={`Battery: ${fmtNum(drone.battery?.voltage, 1)} V`}
          />
          <Metric
            label="LAG"
            value={fmtNum(droneLat, 0)}
            unit=" ms"
            color={LatColor(droneLat)}
            title="Telemetry latency"
          />

          <Divider />
        </>
      )}

      {/* ── BOT section ── */}
      {bot && (
        <>
          <div className="lmb-section-label" style={{ color: "var(--bot-color)" }}>
            🤖 {bot.robot_id.replace(/_/g, " ").toUpperCase()}
          </div>

          {bot.mode && (
            <Metric label="MODE" value={bot.mode} color="var(--accent-bright)" title="Current mode" />
          )}
          <Metric label="X" value={fmtNum(bot.pose.x, 2)} unit=" m" title="Local X (East) position" />
          <Metric label="Y" value={fmtNum(bot.pose.y, 2)} unit=" m" title="Local Y (North) position" />
          <Metric label="HDG" value={fmtNum((bot.pose.yaw * 180) / Math.PI, 0)} unit="°" title="Heading (yaw)" />
          {bot.velocity && (
            <>
              <Metric
                label="VEL"
                value={fmtNum(bot.velocity.linear_x, 2)}
                unit=" m/s"
                title="Linear velocity"
              />
              <Metric
                label="ω"
                value={fmtNum(bot.velocity.angular_z, 2)}
                unit=" r/s"
                title="Angular velocity"
              />
            </>
          )}
          <Metric
            label="BATT"
            value={fmtNum(bot.battery?.percentage, 0)}
            unit="%"
            color={BattColor(bot.battery?.percentage)}
            title="Battery percentage"
          />
          <Metric
            label="LAG"
            value={fmtNum(botLat, 0)}
            unit=" ms"
            color={LatColor(botLat)}
            title="Telemetry latency"
          />

          <Divider />
        </>
      )}
      {!bot && (
        <>
          <div className="lmb-section-label" style={{ color: "var(--bot-color)" }}>
            🤖 {(anyBot?.robot_id ?? "turtlebot").replace(/_/g, " ").toUpperCase()}
          </div>
          <Metric
            label="STATUS"
            value={botStatus}
            color={botStatus === "AWAITING /ODOM" ? "var(--warn)" : "var(--text-2)"}
            title={
              botStatus === "AWAITING /ODOM"
                ? "Bridge connected, but no /odom data has arrived. On the robot run: ros2 topic hz /odom"
                : "TurtleBot is not streaming telemetry"
            }
          />
          <Divider />
        </>
      )}

      {/* ── COMMON metrics ── */}
      {(drone || bot) && (
        <>
          <div className="lmb-section-label" style={{ color: "var(--text-2)" }}>MISSION</div>
          <MissionHealthGauge />
          <Divider />
          <Metric
            label="SEP"
            value={fmtNum(coord.separation_m, 1)}
            unit=" m"
            color={
              coord.separation_m == null ? "var(--text-2)"
              : Math.abs(coord.separation_m - (coord.target_separation_m ?? 3)) < 1 ? "var(--ok)"
              : "var(--warn)"
            }
            title={`Actual / target separation: ${fmtNum(coord.target_separation_m, 1)} m`}
          />
          <Metric
            label="ERR"
            value={fmtNum(coord.tracking_error_m, 2)}
            unit=" m"
            color={
              coord.tracking_error_m == null ? "var(--text-2)"
              : coord.tracking_error_m < 1.5 ? "var(--ok)"
              : coord.tracking_error_m < 3 ? "var(--warn)" : "var(--crit)"
            }
            title="Tracking error"
          />
          {/* Prediction indicator — only shown when backend predicts a problem */}
          {coord.predicted_tracking_error_m != null && coord.predicted_tracking_error_m > 1.0 && (
            <Metric
              label="PRED"
              value={fmtNum(coord.predicted_separation_m, 1)}
              unit=" m"
              color={coord.predicted_tracking_error_m >= 2.0 ? "var(--warn)" : "var(--text-1)"}
              title={`Predicted separation in ~3s (trend: ${coord.separation_trend ?? "—"})`}
            />
          )}
          <Metric
            label="STATE"
            value={coord.state}
            color={coord.state === "TRACKING" ? "var(--ok)" : coord.state === "IDLE" ? "var(--text-2)" : "var(--warn)"}
          />
        </>
      )}
    </div>
  );
}
