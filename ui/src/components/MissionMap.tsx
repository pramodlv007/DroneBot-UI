import { useMemo, useRef, useState, useCallback } from "react";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import type { RobotState } from "@/types/robot";
import type { CoordinationState } from "@/types/coordination";
import { fmtNum, robotLabel } from "@/utils/format";
import GeographicMap from "./GeographicMap";

type ViewMode = "LOCAL" | "GEOGRAPHIC";
const PADDING_M = 3.0;
const TRAIL_MAX = 40;

export default function MissionMap() {
  const robots = useRobotStore((s) => s.robots);
  const coordination = useCoordinationStore((s) => s.coordination);
  const [mode, setMode] = useState<ViewMode>("LOCAL");

  const robotList = useMemo(() => Object.values(robots), [robots]);
  const hasGps = robotList.some((r) => r.gps !== null);

  return (
    <div className="panel map-panel">
      <div className="panel-title-row">
        <div className="panel-title" style={{ margin: 0 }}>Position</div>
        <div className="map-toggle">
          <button className={mode === "LOCAL" ? "primary" : ""} onClick={() => setMode("LOCAL")}>
            Local
          </button>
          <button
            className={mode === "GEOGRAPHIC" ? "primary" : ""}
            onClick={() => setMode("GEOGRAPHIC")}
            disabled={!hasGps}
            title={hasGps ? "" : "No robot is reporting GPS"}
          >
            GPS
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
  const trailsRef = useRef<Record<string, { x: number; y: number }[]>>({});
  const [zoom, setZoom] = useState(1.0);

  // Update trails
  robots.forEach((r) => {
    if (!trailsRef.current[r.robot_id]) trailsRef.current[r.robot_id] = [];
    const trail = trailsRef.current[r.robot_id];
    const last = trail[trail.length - 1];
    const dx = r.pose.x - (last?.x ?? r.pose.x + 999);
    const dy = r.pose.y - (last?.y ?? r.pose.y + 999);
    if (!last || Math.sqrt(dx * dx + dy * dy) > 0.05) {
      trail.push({ x: r.pose.x, y: r.pose.y });
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
          stroke={isMajor ? "rgba(180,190,205,0.18)" : "rgba(180,190,205,0.07)"}
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
          stroke={isMajor ? "rgba(180,190,205,0.18)" : "rgba(180,190,205,0.07)"}
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

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      {/* Zoom controls */}
      <div style={{
        position: "absolute", top: 6, right: 6, zIndex: 5,
        display: "flex", flexDirection: "column", gap: 3,
      }}>
        <button aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(z * 1.4, 10))}
          style={{ width: 26, height: 26, padding: 0, fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>+</button>
        <button aria-label="Fit map to robots" onClick={() => setZoom(1)} title="Reset zoom"
          style={{ width: 26, height: 26, padding: 0, fontSize: 9, letterSpacing: 0 }}>FIT</button>
        <button aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(z / 1.4, 0.2))}
          style={{ width: 26, height: 26, padding: 0, fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>−</button>
      </div>

      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid meet"
        style={{ width: "100%", height: "100%" }}
      >
        {/* Grid */}
        {gridLines}

        {/* Compass labels */}
        <text x={50} y={2.5} textAnchor="middle" fontSize={2.5} fill="rgba(94,174,255,0.5)" fontWeight="bold">N</text>
        <text x={50} y={99.5} textAnchor="middle" fontSize={2.5} fill="rgba(90,112,144,0.4)">S</text>
        <text x={1} y={51} fontSize={2.5} fill="rgba(90,112,144,0.4)">W</text>
        <text x={97} y={51} fontSize={2.5} fill="rgba(90,112,144,0.4)">E</text>

        {/* Tracking / separation line between leader and follower */}
        {bothPresent && (() => {
          const lp = project(leader.pose.x, leader.pose.y);
          const fp = project(follower.pose.x, follower.pose.y);
          const mx = (lp.sx + fp.sx) / 2;
          const my = (lp.sy + fp.sy) / 2;
          return (
            <g>
              <line
                x1={lp.sx} y1={lp.sy}
                x2={fp.sx} y2={fp.sy}
                stroke="rgba(94,174,255,0.35)"
                strokeWidth={0.4}
                strokeDasharray="1.5 1"
              />
              <text x={mx} y={my - 1} textAnchor="middle" fontSize={2.4} fill="rgba(94,174,255,0.7)">
                {fmtNum(coordination.separation_m, 1, " m")}
              </text>
            </g>
          );
        })()}

        {/* Robot trails */}
        {robots.map((r) => {
          const trail = trailsRef.current[r.robot_id] ?? [];
          if (trail.length < 2) return null;
          const isUav = r.robot_type === "UAV";
          const baseColor = isUav ? "94,174,255" : "168,85,247";
          const pts = trail.map((p) => {
            const { sx, sy } = project(p.x, p.y);
            return `${sx.toFixed(1)},${sy.toFixed(1)}`;
          }).join(" ");
          return (
            <polyline
              key={`trail-${r.robot_id}`}
              points={pts}
              fill="none"
              stroke={`rgba(${baseColor},0.25)`}
              strokeWidth={0.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          );
        })}

        {/* Robot markers */}
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

          return (
            <g key={r.robot_id} transform={`translate(${sx}, ${sy})`}>
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
            <text x={50} y={50} textAnchor="middle" fontSize={3.5} fill="var(--text-2)">
              No robots connected
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
