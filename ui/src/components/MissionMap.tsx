import { useMemo, useState } from "react";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import type { RobotState } from "@/types/robot";
import type { CoordinationState } from "@/types/coordination";
import { robotLabel } from "@/utils/format";
import GeographicMap from "./GeographicMap";

type ViewMode = "LOCAL" | "GEOGRAPHIC";

const PADDING_M = 2.0;

export default function MissionMap() {
  const robots = useRobotStore((s) => s.robots);
  const coordination = useCoordinationStore((s) => s.coordination);
  const [mode, setMode] = useState<ViewMode>("LOCAL");

  const robotList = useMemo(() => Object.values(robots), [robots]);
  const hasGps = robotList.some((r) => r.gps !== null);

  return (
    <div className="panel map-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div className="panel-title">Shared Mission View</div>
        <div className="map-toggle">
          <button className={mode === "LOCAL" ? "primary" : ""} onClick={() => setMode("LOCAL")}>
            LOCAL FRAME
          </button>
          <button
            className={mode === "GEOGRAPHIC" ? "primary" : ""}
            onClick={() => setMode("GEOGRAPHIC")}
            disabled={!hasGps}
            title={hasGps ? "" : "No robot is reporting GPS"}
          >
            GEOGRAPHIC
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

export function LocalFrameMap({ robots, coordination }: { robots: RobotState[]; coordination: CoordinationState }) {
  const xs = robots.map((r) => r.pose.x);
  const ys = robots.map((r) => r.pose.y);
  const minX = xs.length ? Math.min(...xs) - PADDING_M : -5;
  const maxX = xs.length ? Math.max(...xs) + PADDING_M : 5;
  const minY = ys.length ? Math.min(...ys) - PADDING_M : -5;
  const maxY = ys.length ? Math.max(...ys) + PADDING_M : 5;

  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  const span = Math.max(spanX, spanY);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const half = span / 2;

  const viewMinX = cx - half;
  const viewMinY = cy - half;

  // SVG y-axis points down; mission_map y is North(+)/up, so flip.
  const project = (x: number, y: number) => ({
    sx: ((x - viewMinX) / span) * 100,
    sy: 100 - ((y - viewMinY) / span) * 100,
  });

  const gridLines = [];
  const step = span > 20 ? 5 : span > 8 ? 2 : 1;
  for (let g = Math.ceil(viewMinX / step) * step; g <= viewMinX + span; g += step) {
    const { sx } = project(g, 0);
    gridLines.push(<line key={`vx${g}`} x1={sx} y1={0} x2={sx} y2={100} className="grid-line" />);
  }
  for (let g = Math.ceil(viewMinY / step) * step; g <= viewMinY + span; g += step) {
    const { sy } = project(0, g);
    gridLines.push(<line key={`hy${g}`} x1={0} y1={sy} x2={100} y2={sy} className="grid-line" />);
  }

  const leader = robots.find((r) => r.robot_id === coordination.leader_id);
  const follower = robots.find((r) => r.robot_id === coordination.follower_id);

  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style={{ width: "100%", height: "100%" }}>
      <style>
        {`.grid-line { stroke: var(--border); stroke-width: 0.15; }
          .robot-label { font-size: 3px; fill: var(--text-1); font-family: var(--sans); }
          .track-line { stroke: var(--accent); stroke-width: 0.3; stroke-dasharray: 1,1; }`}
      </style>
      {gridLines}

      {leader && follower && (
        <line
          x1={project(leader.pose.x, leader.pose.y).sx}
          y1={project(leader.pose.x, leader.pose.y).sy}
          x2={project(follower.pose.x, follower.pose.y).sx}
          y2={project(follower.pose.x, follower.pose.y).sy}
          className="track-line"
        />
      )}

      {robots.map((r) => {
        const { sx, sy } = project(r.pose.x, r.pose.y);
        const isUav = r.robot_type === "UAV";
        const color = !r.connected ? "var(--unknown)" : r.health === "CRITICAL" ? "var(--crit)" : r.health === "WARNING" ? "var(--warn)" : "var(--accent)";
        const rot = 90 - (r.pose.yaw * 180) / Math.PI;

        return (
          <g key={r.robot_id} transform={`translate(${sx}, ${sy})`}>
            {isUav ? (
              <polygon
                points="0,-2.6 2.2,2.2 0,1.2 -2.2,2.2"
                fill={color}
                transform={`rotate(${rot})`}
                stroke="#fff"
                strokeWidth={0.15}
              />
            ) : (
              <circle r={1.8} fill={color} stroke="#fff" strokeWidth={0.15} />
            )}
            <text className="robot-label" x={3} y={1}>
              {robotLabel(r.robot_id)}
            </text>
          </g>
        );
      })}

      {robots.length === 0 && (
        <text x={50} y={50} textAnchor="middle" className="robot-label" fill="var(--text-2)">
          No robots connected
        </text>
      )}
    </svg>
  );
}
