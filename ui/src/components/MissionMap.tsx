import { useMemo, useRef, useState, useCallback } from "react";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { useAnomalyStore } from "@/stores/anomalyStore";
import type { RobotState } from "@/types/robot";
import type { CoordinationState } from "@/types/coordination";
import { fmtNum, robotLabel } from "@/utils/format";
import GeographicMap from "./GeographicMap";

type ViewMode = "LOCAL" | "GEOGRAPHIC";
const PADDING_M = 3.0;
const TRAIL_MAX = 60;

// Velocity → color mapping (blue=slow → cyan → green → yellow → red=fast)
function velocityColor(speed: number, maxSpeed: number): string {
  const ratio = Math.min(1, Math.abs(speed) / Math.max(0.01, maxSpeed));
  if (ratio < 0.25) return "rgba(94,174,255,0.6)";
  if (ratio < 0.5) return "rgba(60,215,160,0.7)";
  if (ratio < 0.75) return "rgba(255,200,60,0.8)";
  return "rgba(255,100,80,0.9)";
}

// Tracking state → corridor color
function corridorColor(state: string): string {
  switch (state) {
    case "TRACKING": return "rgba(60,215,120,0.12)";
    case "DEGRADED": return "rgba(255,180,58,0.15)";
    case "LOST":
    case "EMERGENCY": return "rgba(255,80,80,0.18)";
    default: return "rgba(94,174,255,0.08)";
  }
}
function corridorStroke(state: string): string {
  switch (state) {
    case "TRACKING": return "rgba(60,215,120,0.35)";
    case "DEGRADED": return "rgba(255,180,58,0.45)";
    case "LOST":
    case "EMERGENCY": return "rgba(255,80,80,0.5)";
    default: return "rgba(94,174,255,0.2)";
  }
}

interface TrailPoint {
  x: number;
  y: number;
  speed: number; // m/s from VelocityState
}

export default function MissionMap() {
  const robots = useRobotStore((s) => s.robots);
  const coordination = useCoordinationStore((s) => s.coordination);
  const [mode, setMode] = useState<ViewMode>("LOCAL");

  // A ROS2 robot whose bridge has connected but sent no /odom yet only has a
  // placeholder pose at the origin — don't plot that as a real position.
  const robotList = useMemo(() => Object.values(robots).filter((r) => !r.metadata?.awaiting_odom), [robots]);
  const hasGps = robotList.some((r) => r.gps !== null);

  return (
    <div className="panel map-panel">
      <div className="panel-title-row">
        <div className="panel-title" style={{ margin: 0 }}>Live Mission View</div>
        <div className="map-toggle">
          <button className={mode === "LOCAL" ? "primary" : ""} onClick={() => setMode("LOCAL")}>
            LOCAL
          </button>
          <button
            className={mode === "GEOGRAPHIC" ? "primary" : ""}
            onClick={() => setMode("GEOGRAPHIC")}
            disabled={!hasGps}
            title={hasGps ? "" : "No robot is reporting GPS"}
          >
            GPS MAP
          </button>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        {mode === "LOCAL" ? (
          <LocalFrameMap robots={robotList} coordination={coordination} />
        ) : (
          <GeographicMap robots={robotList} />
        )}
      </div>
    </div>
  );
}

export function LocalFrameMap({
  robots,
  coordination,
}: {
  robots: RobotState[];
  coordination: CoordinationState;
}) {
  const trailsRef = useRef<Record<string, TrailPoint[]>>({});
  const activeAnomalies = useAnomalyStore((s) => s.active);
  const [zoom, setZoom] = useState(1.0);
  const [hoveredRobot, setHoveredRobot] = useState<string | null>(null);

  // Update trails with velocity encoding
  robots.forEach((r) => {
    if (!trailsRef.current[r.robot_id]) trailsRef.current[r.robot_id] = [];
    const trail = trailsRef.current[r.robot_id];
    const last = trail[trail.length - 1];
    const dx = r.pose.x - (last?.x ?? r.pose.x + 999);
    const dy = r.pose.y - (last?.y ?? r.pose.y + 999);
    if (!last || Math.sqrt(dx * dx + dy * dy) > 0.05) {
      const speed = r.velocity
        ? Math.hypot(r.velocity.linear_x, r.velocity.linear_y)
        : 0;
      trail.push({ x: r.pose.x, y: r.pose.y, speed });
      if (trail.length > TRAIL_MAX) trail.shift();
    }
  });

  const xs = robots.map((r) => r.pose.x);
  const ys = robots.map((r) => r.pose.y);
  const baseMinX = xs.length ? Math.min(...xs) - PADDING_M : -5;
  const baseMaxX = xs.length ? Math.max(...xs) + PADDING_M : 5;
  const baseMinY = ys.length ? Math.min(...ys) - PADDING_M : -5;
  const baseMaxY = ys.length ? Math.max(...ys) + PADDING_M : 5;

  const rawSpanX = Math.max(1, baseMaxX - baseMinX);
  const rawSpanY = Math.max(1, baseMaxY - baseMinY);
  const rawSpan = Math.max(rawSpanX, rawSpanY) / zoom;
  const cx = (baseMinX + baseMaxX) / 2;
  const cy = (baseMinY + baseMaxY) / 2;
  const half = rawSpan / 2;
  const viewMinX = cx - half;
  const viewMinY = cy - half;
  const span = rawSpan;

  // project world → SVG [0, 100]
  const project = useCallback(
    (x: number, y: number) => ({
      sx: ((x - viewMinX) / span) * 100,
      sy: 100 - ((y - viewMinY) / span) * 100,
    }),
    [viewMinX, viewMinY, span]
  );

  // Grid
  const gridLines = useMemo(() => {
    const lines: JSX.Element[] = [];
    const step = span > 20 ? 5 : span > 8 ? 2 : 1;
    for (let g = Math.ceil(viewMinX / step) * step; g <= viewMinX + span; g += step) {
      const { sx } = project(g, 0);
      const isMajor = g === 0;
      lines.push(
        <line key={`v${g}`} x1={sx} y1={0} x2={sx} y2={100}
          stroke={isMajor ? "rgba(94,174,255,0.18)" : "rgba(30,42,61,0.8)"}
          strokeWidth={isMajor ? 0.3 : 0.15} />
      );
      if (g !== 0)
        lines.push(<text key={`vl${g}`} x={sx + 0.3} y={99} fontSize={2.2} fill="rgba(90,112,144,0.6)">{g}m</text>);
    }
    for (let g = Math.ceil(viewMinY / step) * step; g <= viewMinY + span; g += step) {
      const { sy } = project(0, g);
      const isMajor = g === 0;
      lines.push(
        <line key={`h${g}`} x1={0} y1={sy} x2={100} y2={sy}
          stroke={isMajor ? "rgba(94,174,255,0.18)" : "rgba(30,42,61,0.8)"}
          strokeWidth={isMajor ? 0.3 : 0.15} />
      );
      if (g !== 0)
        lines.push(<text key={`hl${g}`} x={0.5} y={sy - 0.5} fontSize={2.2} fill="rgba(90,112,144,0.6)">{g}m</text>);
    }
    return lines;
  }, [viewMinX, viewMinY, span, project]);

  const leader = robots.find((r) => r.robot_id === coordination.leader_id);
  const follower = robots.find((r) => r.robot_id === coordination.follower_id);
  const bothPresent = leader && follower;

  // Hovered robot data for tooltip
  const hoveredData = hoveredRobot
    ? robots.find((r) => r.robot_id === hoveredRobot)
    : null;

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      {/* Zoom controls */}
      <div style={{
        position: "absolute", top: 6, right: 6, zIndex: 5,
        display: "flex", flexDirection: "column", gap: 3,
      }}>
        <button onClick={() => setZoom((z) => Math.min(z * 1.4, 10))}
          style={{ width: 26, height: 26, padding: 0, fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>+</button>
        <button onClick={() => setZoom(1)} title="Reset zoom"
          style={{ width: 26, height: 26, padding: 0, fontSize: 9, letterSpacing: 0 }}>FIT</button>
        <button onClick={() => setZoom((z) => Math.max(z / 1.4, 0.2))}
          style={{ width: 26, height: 26, padding: 0, fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>−</button>
      </div>

      {/* Hover tooltip — shows real backend telemetry */}
      {hoveredData && (
        <div className="map-tooltip" style={{
          position: "absolute",
          top: 8, left: 8,
          zIndex: 10,
        }}>
          <div className="map-tooltip-title">
            {hoveredData.robot_type === "UAV" ? "🚁" : "🤖"} {robotLabel(hoveredData.robot_id)}
          </div>
          <div className="map-tooltip-grid">
            <span>Position</span>
            <span>{fmtNum(hoveredData.pose.x, 2)}, {fmtNum(hoveredData.pose.y, 2)} m</span>
            {hoveredData.robot_type === "UAV" && (
              <>
                <span>Altitude</span>
                <span>{fmtNum(hoveredData.gps?.altitude ?? hoveredData.pose.z, 1)} m</span>
              </>
            )}
            <span>Heading</span>
            <span>{fmtNum((hoveredData.pose.yaw * 180) / Math.PI, 0)}°</span>
            {hoveredData.velocity && (
              <>
                <span>Speed</span>
                <span>{fmtNum(Math.hypot(hoveredData.velocity.linear_x, hoveredData.velocity.linear_y), 2)} m/s</span>
              </>
            )}
            <span>Battery</span>
            <span style={{ color: (hoveredData.battery?.percentage ?? 100) > 20 ? "var(--ok)" : "var(--crit)" }}>
              {fmtNum(hoveredData.battery?.percentage, 0)}%
            </span>
            <span>Latency</span>
            <span>{fmtNum(hoveredData.received_timestamp_ms - hoveredData.source_timestamp_ms, 0)} ms</span>
            <span>Health</span>
            <span style={{
              color: hoveredData.health === "NORMAL" ? "var(--ok)"
                : hoveredData.health === "WARNING" ? "var(--warn)" : "var(--crit)"
            }}>{hoveredData.health}</span>
          </div>
        </div>
      )}

      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid meet"
        style={{ width: "100%", height: "100%" }}
      >
        <defs>
          <radialGradient id="bg-grad" cx="50%" cy="50%" r="70%">
            <stop offset="0%" stopColor="rgba(13,17,23,0)" />
            <stop offset="100%" stopColor="rgba(8,11,16,0.4)" />
          </radialGradient>
          {/* Pulse animation for corridor in degraded/lost state */}
          <filter id="corridor-glow">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect x={0} y={0} width={100} height={100} fill="url(#bg-grad)" />

        {/* Grid */}
        {gridLines}

        {/* Compass labels */}
        <text x={50} y={2.5} textAnchor="middle" fontSize={2.5} fill="rgba(94,174,255,0.5)" fontWeight="bold">N</text>
        <text x={50} y={99.5} textAnchor="middle" fontSize={2.5} fill="rgba(90,112,144,0.4)">S</text>
        <text x={1} y={51} fontSize={2.5} fill="rgba(90,112,144,0.4)">W</text>
        <text x={97} y={51} fontSize={2.5} fill="rgba(90,112,144,0.4)">E</text>

        {/* ═══ SEPARATION CORRIDOR ═══
            Ellipse showing the target separation zone between leader & follower.
            Color driven by backend coordination.state (TRACKING/DEGRADED/LOST). */}
        {bothPresent && coordination.target_separation_m != null && (() => {
          const lp = project(leader.pose.x, leader.pose.y);
          const fp = project(follower.pose.x, follower.pose.y);
          const mx = (lp.sx + fp.sx) / 2;
          const my = (lp.sy + fp.sy) / 2;
          const dist = Math.hypot(lp.sx - fp.sx, lp.sy - fp.sy);
          const targetPx = (coordination.target_separation_m / span) * 100;
          const angle = Math.atan2(fp.sy - lp.sy, fp.sx - lp.sx) * (180 / Math.PI);
          const isAlerted = coordination.state === "DEGRADED" || coordination.state === "LOST";

          return (
            <g className={isAlerted ? "corridor-pulse" : ""}>
              <ellipse
                cx={mx} cy={my}
                rx={Math.max(dist / 2 + targetPx * 0.3, targetPx * 0.5)}
                ry={targetPx * 0.6}
                fill={corridorColor(coordination.state)}
                stroke={corridorStroke(coordination.state)}
                strokeWidth={0.3}
                strokeDasharray={isAlerted ? "1.5 1" : "2 1.5"}
                transform={`rotate(${angle}, ${mx}, ${my})`}
                filter={isAlerted ? "url(#corridor-glow)" : undefined}
              />
            </g>
          );
        })()}

        {/* Tracking / separation line between leader and follower */}
        {bothPresent && (() => {
          const lp = project(leader.pose.x, leader.pose.y);
          const fp = project(follower.pose.x, follower.pose.y);
          const mx = (lp.sx + fp.sx) / 2;
          const my = (lp.sy + fp.sy) / 2;
          const trendIcon = coordination.separation_trend === "DIVERGING" ? "↗"
            : coordination.separation_trend === "CONVERGING" ? "↘" : "→";
          const trendColor = coordination.separation_trend === "DIVERGING" ? "rgba(255,180,58,0.9)"
            : coordination.separation_trend === "CONVERGING" ? "rgba(60,215,120,0.9)"
            : "rgba(94,174,255,0.7)";
          return (
            <g>
              <line
                x1={lp.sx} y1={lp.sy}
                x2={fp.sx} y2={fp.sy}
                stroke="rgba(94,174,255,0.35)"
                strokeWidth={0.4}
                strokeDasharray="1.5 1"
              />
              <text x={mx} y={my - 1.5} textAnchor="middle" fontSize={2.4} fill="rgba(94,174,255,0.7)">
                {fmtNum(coordination.separation_m, 1, " m")}
              </text>
              {/* Separation trend indicator — driven by backend */}
              {coordination.separation_trend && (
                <text x={mx} y={my + 2.5} textAnchor="middle" fontSize={2} fill={trendColor} fontWeight="bold">
                  {trendIcon} {coordination.separation_trend}
                </text>
              )}
            </g>
          );
        })()}

        {/* ═══ VELOCITY-ENCODED TRAILS ═══
            Trail color & width reflect actual velocity from VelocityState.
            Each segment is individually colored: blue(slow) → green → yellow → red(fast). */}
        {robots.map((r) => {
          const trail = trailsRef.current[r.robot_id] ?? [];
          if (trail.length < 2) return null;
          const maxSpeed = r.robot_type === "UAV" ? 2.0 : 0.22;

          return (
            <g key={`trail-${r.robot_id}`}>
              {trail.slice(1).map((pt, i) => {
                const prev = trail[i];
                const p1 = project(prev.x, prev.y);
                const p2 = project(pt.x, pt.y);
                const age = 1 - (i / trail.length); // older = more transparent
                const color = velocityColor(pt.speed, maxSpeed);
                const width = 0.3 + (pt.speed / maxSpeed) * 0.8;
                return (
                  <line
                    key={i}
                    x1={p1.sx} y1={p1.sy}
                    x2={p2.sx} y2={p2.sy}
                    stroke={color}
                    strokeWidth={width}
                    strokeLinecap="round"
                    opacity={0.15 + age * 0.7}
                  />
                );
              })}
              {/* Direction arrows along trail every 8 points */}
              {trail.filter((_, i) => i > 0 && i % 8 === 0).map((pt, i) => {
                const prev = trail[Math.max(0, trail.indexOf(pt) - 1)];
                const p = project(pt.x, pt.y);
                const angle = Math.atan2(pt.y - prev.y, pt.x - prev.x) * (180 / Math.PI);
                const isUav = r.robot_type === "UAV";
                return (
                  <polygon
                    key={`arr-${i}`}
                    points="0,-0.8 0.6,0.8 -0.6,0.8"
                    fill={isUav ? "rgba(94,174,255,0.4)" : "rgba(168,85,247,0.4)"}
                    transform={`translate(${p.sx},${p.sy}) rotate(${90 - angle})`}
                  />
                );
              })}
            </g>
          );
        })}

        {/* ═══ ALTITUDE SHADOW (2.5D) ═══
            For UAVs: render a ground-level shadow + vertical dashed line.
            Shadow size scales with pose.z (real altitude from backend). */}
        {robots.filter((r) => r.robot_type === "UAV" && r.connected).map((r) => {
          const alt = r.gps?.altitude ?? r.pose.z;
          if (alt < 0.5) return null; // too low to show shadow
          const { sx, sy } = project(r.pose.x, r.pose.y);
          const shadowRadius = Math.min(6, 1.5 + alt * 0.4);
          const shadowOffset = Math.min(4, alt * 0.3); // shadow drops lower at higher alt
          return (
            <g key={`shadow-${r.robot_id}`}>
              {/* Ground shadow */}
              <ellipse
                cx={sx} cy={sy + shadowOffset}
                rx={shadowRadius} ry={shadowRadius * 0.4}
                fill="rgba(0,0,0,0.15)"
                stroke="rgba(94,174,255,0.1)"
                strokeWidth={0.15}
              />
              {/* Vertical altitude line */}
              <line
                x1={sx} y1={sy}
                x2={sx} y2={sy + shadowOffset}
                stroke="rgba(94,174,255,0.25)"
                strokeWidth={0.2}
                strokeDasharray="0.5 0.5"
              />
              {/* Altitude label */}
              <text
                x={sx + shadowRadius + 0.5} y={sy + shadowOffset + 1}
                fontSize={1.8} fill="rgba(94,174,255,0.5)"
              >
                {fmtNum(alt, 1)}m ↕
              </text>
            </g>
          );
        })}

        {/* ═══ PREDICTION GHOST MARKERS ═══
            When backend predicts separation will exceed threshold,
            show semi-transparent "ghost" markers at predicted positions. */}
        {bothPresent && coordination.predicted_tracking_error_m != null &&
          coordination.predicted_tracking_error_m > 1.0 &&
          leader.velocity && follower.velocity && (() => {
            // Compute predicted positions (same logic as backend, 3s horizon)
            const h = 3.0;
            const lType = leader.robot_type;
            const fType = follower.robot_type;

            const toMission = (vx: number, vy: number, yaw: number, isUgv: boolean) => {
              if (!isUgv) return { mx: vx, my: vy };
              return {
                mx: vx * Math.cos(yaw) - vy * Math.sin(yaw),
                my: vx * Math.sin(yaw) + vy * Math.cos(yaw),
              };
            };
            const lv = toMission(leader.velocity!.linear_x, leader.velocity!.linear_y, leader.pose.yaw, lType === "UGV");
            const fv = toMission(follower.velocity!.linear_x, follower.velocity!.linear_y, follower.pose.yaw, fType === "UGV");

            const plx = leader.pose.x + lv.mx * h;
            const ply = leader.pose.y + lv.my * h;
            const pfx = follower.pose.x + fv.mx * h;
            const pfy = follower.pose.y + fv.my * h;

            const lGhost = project(plx, ply);
            const fGhost = project(pfx, pfy);
            const isWarning = coordination.predicted_tracking_error_m! >= 2.0;
            const ghostColor = isWarning ? "rgba(255,180,58,0.35)" : "rgba(94,174,255,0.25)";

            return (
              <g className="ghost-pulse">
                {/* Predicted position - leader */}
                <circle cx={lGhost.sx} cy={lGhost.sy} r={2} fill="none"
                  stroke={ghostColor} strokeWidth={0.3} strokeDasharray="1 0.8" />
                <text x={lGhost.sx} y={lGhost.sy - 3} textAnchor="middle" fontSize={1.8}
                  fill={ghostColor}>~3s</text>

                {/* Predicted position - follower */}
                <circle cx={fGhost.sx} cy={fGhost.sy} r={2} fill="none"
                  stroke={ghostColor} strokeWidth={0.3} strokeDasharray="1 0.8" />

                {/* Predicted separation line */}
                <line x1={lGhost.sx} y1={lGhost.sy} x2={fGhost.sx} y2={fGhost.sy}
                  stroke={isWarning ? "rgba(255,180,58,0.3)" : "rgba(94,174,255,0.2)"}
                  strokeWidth={0.3} strokeDasharray="0.8 0.8" />
                <text
                  x={(lGhost.sx + fGhost.sx) / 2}
                  y={(lGhost.sy + fGhost.sy) / 2 - 1.5}
                  textAnchor="middle" fontSize={2}
                  fill={isWarning ? "rgba(255,180,58,0.8)" : "rgba(94,174,255,0.6)"}
                  fontWeight="bold"
                >
                  ⚠ {fmtNum(coordination.predicted_separation_m, 1)}m
                </text>
              </g>
            );
          })()}

        {/* ═══ ROBOT MARKERS with heading cone ═══ */}
        {robots.map((r) => {
          const { sx, sy } = project(r.pose.x, r.pose.y);
          const isUav = r.robot_type === "UAV";
          const connected = r.connected;
          const glowColor = isUav ? "rgba(94,174,255,0.5)" : "rgba(168,85,247,0.5)";
          const fillColor = !connected
            ? "rgba(74,90,116,0.8)"
            : r.health === "CRITICAL" ? "var(--crit)"
            : r.health === "WARNING" ? "var(--warn)"
            : isUav ? "var(--drone-color)" : "var(--bot-color)";
          const rot = 90 - (r.pose.yaw * 180) / Math.PI;
          const deadReckoning = !!r.metadata?.dead_reckoning_active;
          const yawDeg = (r.pose.yaw * 180) / Math.PI;
          const anomalies = activeAnomalies[r.robot_id] ?? [];
          const hasAnomaly = anomalies.length > 0;

          return (
            <g key={r.robot_id} transform={`translate(${sx}, ${sy})`}
              onMouseEnter={() => setHoveredRobot(r.robot_id)}
              onMouseLeave={() => setHoveredRobot(null)}
              style={{ cursor: "pointer" }}
            >
              {/* ── Heading cone (±20°) — shows where robot is aimed ── */}
              {connected && (
                <path
                  d={(() => {
                    const coneHalf = 20; // degrees
                    const coneLen = 6; // SVG units
                    const startAngle = (-(yawDeg + coneHalf) + 90) * (Math.PI / 180);
                    const endAngle = (-(yawDeg - coneHalf) + 90) * (Math.PI / 180);
                    const x1 = Math.cos(startAngle) * coneLen;
                    const y1 = -Math.sin(startAngle) * coneLen;
                    const x2 = Math.cos(endAngle) * coneLen;
                    const y2 = -Math.sin(endAngle) * coneLen;
                    return `M0,0 L${x1.toFixed(2)},${y1.toFixed(2)} A${coneLen},${coneLen} 0 0,1 ${x2.toFixed(2)},${y2.toFixed(2)} Z`;
                  })()}
                  fill={isUav ? "rgba(94,174,255,0.06)" : "rgba(168,85,247,0.06)"}
                  stroke={isUav ? "rgba(94,174,255,0.12)" : "rgba(168,85,247,0.12)"}
                  strokeWidth={0.15}
                />
              )}

              {/* Glow ring — dashed while position is a dead-reckoning
                  estimate rather than real GPS/EKF data */}
              {connected && (
                <circle
                  r={4} fill="none" stroke={deadReckoning ? "var(--warn)" : glowColor}
                  strokeWidth={0.5} strokeDasharray={deadReckoning ? "1 0.8" : undefined} opacity={0.8}
                />
              )}
              {deadReckoning && (
                <text x={0} y={-6} textAnchor="middle" fontSize={2.2} fill="var(--warn)" fontWeight="bold">
                  DR EST.
                </text>
              )}

              {/* Anomaly indicator — pulsing ring + label, driven by the
                  backend's AnomalyDetector (real ongoing state, not a
                  one-off toast) */}
              {hasAnomaly && (
                <g className="anomaly-marker-pulse">
                  <circle r={5.5} fill="none" stroke="var(--crit)" strokeWidth={0.4} strokeDasharray="0.8 0.6" />
                  <text x={0} y={7.5} textAnchor="middle" fontSize={2.2} fill="var(--crit)" fontWeight="bold">
                    {anomalies[0]}
                  </text>
                </g>
              )}

              {isUav ? (
                /* Drone: arrow shape pointing in yaw direction */
                <polygon
                  points="0,-3 2.5,2.5 0,1.5 -2.5,2.5"
                  fill={fillColor}
                  transform={`rotate(${rot})`}
                  stroke="rgba(255,255,255,0.5)"
                  strokeWidth={0.2}
                />
              ) : (
                /* TurtleBot: circle with direction arrow */
                <g transform={`rotate(${rot})`}>
                  <circle r={2.2} fill={fillColor} stroke="rgba(255,255,255,0.4)" strokeWidth={0.2} />
                  <line x1={0} y1={-2.2} x2={0} y2={-4} stroke="rgba(255,255,255,0.6)" strokeWidth={0.5} />
                </g>
              )}

              {/* Hover highlight ring */}
              {hoveredRobot === r.robot_id && (
                <circle r={5} fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth={0.3}
                  strokeDasharray="1.5 1" className="hover-ring-pulse" />
              )}

              {/* Robot label */}
              <text
                x={3.5} y={1.2}
                fontSize={2.8}
                fill="rgba(232,240,255,0.85)"
                style={{ fontFamily: "var(--sans)", fontWeight: 600 }}
              >
                {robotLabel(r.robot_id)}
              </text>
            </g>
          );
        })}

        {/* Empty state */}
        {robots.length === 0 && (
          <g>
            {/* Animated radar sweep */}
            <circle cx={50} cy={50} r={18} fill="none" stroke="rgba(30,42,61,0.8)" strokeWidth={0.5} />
            <circle cx={50} cy={50} r={10} fill="none" stroke="rgba(30,42,61,0.8)" strokeWidth={0.5} />
            <circle cx={50} cy={50} r={4} fill="rgba(94,174,255,0.15)" />
            <line x1={50} y1={50} x2={50} y2={32} stroke="rgba(94,174,255,0.4)" strokeWidth={0.4}>
              <animateTransform
                attributeName="transform" type="rotate"
                from="0 50 50" to="360 50 50"
                dur="3s" repeatCount="indefinite"
              />
            </line>
            <text x={50} y={74} textAnchor="middle" fontSize={3.5} fill="rgba(90,112,144,0.6)">
              No robots connected
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
