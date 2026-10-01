/**
 * TelemetryHistoryPanel — live sparkline time-series charts.
 * Uses pure SVG path rendering (no charting library).
 * Tracks last 60s of key metrics per robot.
 */
import { useEffect, useRef, useState } from "react";
import { useRobotStore } from "@/stores/robotStore";
import { fmtNum } from "@/utils/format";

const WINDOW_MS = 60_000; // 60 second rolling window
const MAX_PTS = 600;       // 10hz * 60s

interface DataPoint {
  t: number;
  v: number | null;
}

interface RobotHistory {
  altitude: DataPoint[];
  battery: DataPoint[];
  latency: DataPoint[];
  linearVel: DataPoint[];
  angularVel: DataPoint[];
}

function push(arr: DataPoint[], t: number, v: number | null): DataPoint[] {
  const next = [...arr, { t, v }];
  if (next.length > MAX_PTS) next.shift();
  return next;
}

/** Pure SVG sparkline */
function Sparkline({
  data, color, width = 120, height = 28,
}: {
  data: DataPoint[];
  color: string;
  width?: number;
  height?: number;
  unit?: string;
}) {
  const now = Date.now();
  const points = data.filter((p) => p.v !== null && now - p.t < WINDOW_MS);
  if (points.length < 2) {
    return (
      <svg width={width} height={height} className="sparkline-svg">
        <text x={2} y={height / 2 + 4} fontSize={9} fill="var(--text-3)">no data</text>
      </svg>
    );
  }

  const vals = points.map((p) => p.v as number);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const span = maxV === minV ? 1 : maxV - minV;

  const tMin = points[0].t;
  const tMax = Math.max(points[points.length - 1].t, tMin + 1);

  const project = (p: DataPoint): [number, number] => {
    const x = ((p.t - tMin) / (tMax - tMin)) * width;
    const y = height - ((((p.v as number) - minV) / span) * (height - 4)) - 2;
    return [x, y];
  };

  const pathD = points
    .map((p, i) => {
      const [x, y] = project(p);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Fill under the line
  const [lastX, lastY] = project(points[points.length - 1]);
  const [firstX] = project(points[0]);
  const fillD = `${pathD} L${lastX},${height} L${firstX},${height} Z`;

  return (
    <svg width={width} height={height} className="sparkline-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`sg-${color.replace(/[^a-z0-9]/gi, "")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.01" />
        </linearGradient>
      </defs>
      <path d={fillD} fill={`url(#sg-${color.replace(/[^a-z0-9]/gi, "")})`} />
      <path d={pathD} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {/* Dot at latest value */}
      <circle cx={lastX} cy={lastY} r={2.5} fill={color} />
    </svg>
  );
}

interface SparkRowProps {
  label: string;
  data: DataPoint[];
  color: string;
  unit?: string;
  digits?: number;
}

function SparkRow({ label, data, color, unit = "", digits = 1 }: SparkRowProps) {
  const latest = [...data].reverse().find((p) => p.v !== null)?.v ?? null;
  return (
    <div className="sparkline-row">
      <span className="sparkline-label">{label}</span>
      <Sparkline data={data} color={color} width={120} height={26} unit={unit} />
      <span className="sparkline-value">{fmtNum(latest, digits, unit)}</span>
    </div>
  );
}

export default function TelemetryHistoryPanel() {
  const robots = useRobotStore((s) => s.robots);
  const historyRef = useRef<Record<string, RobotHistory>>({});
  const [, setTick] = useState(0); // force re-render

  useEffect(() => {
    const t = setInterval(() => {
      const h = historyRef.current;
      const now = Date.now();

      Object.values(robots).forEach((r) => {
        if (!h[r.robot_id]) {
          h[r.robot_id] = { altitude: [], battery: [], latency: [], linearVel: [], angularVel: [] };
        }
        const rh = h[r.robot_id];
        const latency = r.received_timestamp_ms - r.source_timestamp_ms;
        rh.altitude  = push(rh.altitude,  now, r.gps?.altitude ?? null);
        rh.battery   = push(rh.battery,   now, r.battery?.percentage ?? null);
        rh.latency   = push(rh.latency,   now, latency >= 0 ? latency : null);
        rh.linearVel = push(rh.linearVel, now, r.velocity?.linear_x ?? null);
        rh.angularVel= push(rh.angularVel,now, r.velocity?.angular_z ?? null);
      });

      setTick((n) => n + 1);
    }, 200); // 5hz sample rate for sparklines

    return () => clearInterval(t);
  }, [robots]);

  const robotList = Object.values(robots);
  if (robotList.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
      {robotList.map((r) => {
        const h = historyRef.current[r.robot_id];
        if (!h) return null;
        const isUav = r.robot_type === "UAV";
        const accent = isUav ? "var(--drone-color)" : "var(--bot-color)";

        return (
          <div key={r.robot_id} style={{
            background: "var(--bg-2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "10px 12px",
            boxShadow: "var(--shadow-card)",
          }}>
            <div style={{
              fontSize: 10,
              fontWeight: 800,
              letterSpacing: "0.08em",
              marginBottom: 8,
              color: isUav ? "var(--drone-color)" : "var(--bot-color)",
              textTransform: "uppercase",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}>
              <span>{isUav ? "🚁" : "🤖"}</span>
              <span>{r.robot_id.replace(/_/g, " ")} · Telemetry History</span>
            </div>
            <div className="sparkline-panel">
              {isUav && (
                <SparkRow label="Altitude" data={h.altitude} color={accent} unit=" m" digits={1} />
              )}
              {!isUav && (
                <SparkRow label="Lin. Vel" data={h.linearVel} color={accent} unit=" m/s" digits={2} />
              )}
              {!isUav && (
                <SparkRow label="Ang. Vel" data={h.angularVel} color="#7c3aed" unit=" r/s" digits={2} />
              )}
              <SparkRow label="Battery" data={h.battery} color="var(--ok)" unit="%" digits={0} />
              <SparkRow label="Latency" data={h.latency} color="var(--warn)" unit=" ms" digits={0} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
