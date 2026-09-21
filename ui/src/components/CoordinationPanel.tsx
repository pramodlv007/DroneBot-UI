import { useCoordinationStore } from "@/stores/coordinationStore";
import { fmtNum, robotLabel } from "@/utils/format";
import LatencyPanel from "./LatencyPanel";

const STATE_BADGE: Record<string, string> = {
  TRACKING: "NORMAL",
  IDLE: "UNKNOWN",
  DEGRADED: "WARNING",
  LOST: "CRITICAL",
  EMERGENCY: "CRITICAL",
};

function GaugeBar({ value, max, colorClass }: { value: number; max: number; colorClass: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="gauge-bar-track" style={{ flex: 1 }}>
      <div className={`gauge-bar-fill ${colorClass}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function getTrackingColor(err: number | null): "ok" | "warn" | "crit" {
  if (err === null) return "ok";
  if (err < 1.5) return "ok";
  if (err < 3.0) return "warn";
  return "crit";
}

/** Mini sparkline for separation history — uses real data from coordinationStore.history */
function SeparationSparkline({ targetSep }: { targetSep: number | null }) {
  const history = useCoordinationStore((s) => s.history);
  const recent = history.slice(-60); // ~6s at 10Hz
  if (recent.length < 3) return null;

  const seps = recent.map((h) => h.separation ?? 0);
  const minV = Math.min(...seps, targetSep ?? Infinity) * 0.8;
  const maxV = Math.max(...seps, targetSep ?? 0) * 1.2 || 1;
  const w = 140, h = 28;

  const project = (i: number, v: number): [number, number] => [
    (i / (recent.length - 1)) * w,
    h - ((v - minV) / (maxV - minV)) * (h - 4) - 2,
  ];

  const pathD = seps.map((v, i) => {
    const [x, y] = project(i, v);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  // Target separation reference line
  const targetY = targetSep != null
    ? h - ((targetSep - minV) / (maxV - minV)) * (h - 4) - 2
    : null;

  return (
    <div style={{ margin: "6px 0 2px" }}>
      <div style={{ fontSize: 9, color: "var(--text-2)", marginBottom: 2, fontWeight: 700, textTransform: "uppercase" as const }}>
        Separation History
      </div>
      <svg width={w} height={h} style={{ display: "block" }}>
        {/* Target reference line */}
        {targetY != null && (
          <line x1={0} y1={targetY} x2={w} y2={targetY}
            stroke="rgba(60,215,120,0.3)" strokeWidth={0.5} strokeDasharray="3 2" />
        )}
        {/* Sparkline */}
        <path d={pathD} stroke="var(--accent)" strokeWidth={1.2} fill="none" strokeLinecap="round" />
        {/* Latest dot */}
        {(() => {
          const [lx, ly] = project(seps.length - 1, seps[seps.length - 1]);
          return <circle cx={lx} cy={ly} r={2} fill="var(--accent)" />;
        })()}
      </svg>
    </div>
  );
}

/** Trend indicator badge — driven by backend separation_trend computation */
function TrendBadge({ trend, predictedSep }: { trend: string | null; predictedSep: number | null }) {
  if (!trend) return null;
  const icon = trend === "DIVERGING" ? "↗" : trend === "CONVERGING" ? "↘" : "→";
  const color = trend === "DIVERGING" ? "var(--warn)"
    : trend === "CONVERGING" ? "var(--ok)" : "var(--text-2)";
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6,
      padding: "4px 8px", borderRadius: 4,
      background: trend === "DIVERGING" ? "rgba(255,180,58,0.08)" : "var(--surface-2)",
      marginBottom: 6,
    }}>
      <span style={{ fontSize: 14 }}>{icon}</span>
      <span style={{ fontSize: 10, color, fontWeight: 700, fontFamily: "var(--mono)" }}>{trend}</span>
      {predictedSep != null && (
        <span style={{ fontSize: 9, color: "var(--text-2)", marginLeft: "auto" }}>
          ~3s: {fmtNum(predictedSep, 1)} m
        </span>
      )}
    </div>
  );
}

export default function CoordinationPanel() {
  const c = useCoordinationStore((s) => s.coordination);

  const trackColor = getTrackingColor(c.tracking_error_m);
  const sepMax = Math.max((c.target_separation_m ?? 3) * 2, 5);
  const sepColor: "ok" | "warn" | "crit" =
    c.separation_m < (c.target_separation_m ?? 3) * 1.5 ? "ok"
    : c.separation_m < (c.target_separation_m ?? 3) * 2 ? "warn"
    : "crit";

  const badgeClass = STATE_BADGE[c.state] ?? "UNKNOWN";

  return (
    <div className="panel coordination-panel">
      <div className="panel-title-row">
        <div className="panel-title" style={{ margin: 0 }}>Coordination</div>
        <span className={`badge ${badgeClass}`}
          style={{ animation: c.state === "EMERGENCY" ? "dot-crit 1s infinite" : undefined }}>
          {c.state}
        </span>
      </div>

      {/* Leader → Follower diagram */}
      {(c.leader_id || c.follower_id) && (
        <div className="role-diagram">
          <div className="role-chip">
            <div className="role-label">Leader</div>
            <div className="role-name">{c.leader_id ? robotLabel(c.leader_id) : "—"}</div>
          </div>
          <div className="role-arrow">→</div>
          <div className="role-chip">
            <div className="role-label">Follower</div>
            <div className="role-name">{c.follower_id ? robotLabel(c.follower_id) : "—"}</div>
          </div>
        </div>
      )}

      {/* Metrics with visual gauges */}
      {c.mode === "ATTITUDE_FOLLOW" ? (
        <div>
          {c.motion_intent && (
            <div style={{
              background: "var(--surface-2)", padding: "6px 10px", borderRadius: 4,
              marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center"
            }}>
              <span style={{ fontSize: 10, color: "var(--text-2)", textTransform: "uppercase", fontWeight: 700 }}>Intent</span>
              <span style={{ fontSize: 11, color: "var(--accent)", fontWeight: 700, fontFamily: "var(--mono)" }}>
                {c.motion_intent}
              </span>
            </div>
          )}

          <div className="coord-metric">
            <span className="label">Drone Pitch</span>
            <GaugeBar value={Math.abs(c.drone_pitch_deg ?? 0)} max={30} colorClass={Math.abs(c.drone_pitch_deg ?? 0) < 5 ? "ok" : "warn"} />
            <span className="val">{fmtNum(c.drone_pitch_deg, 1, "°")}</span>
          </div>

          <div className="coord-metric">
            <span className="label">Drone Roll</span>
            <GaugeBar value={Math.abs(c.drone_roll_deg ?? 0)} max={30} colorClass={Math.abs(c.drone_roll_deg ?? 0) < 5 ? "ok" : "warn"} />
            <span className="val">{fmtNum(c.drone_roll_deg, 1, "°")}</span>
          </div>

          <div className="coord-metric">
            <span className="label">Drone Yaw</span>
            <span style={{ flex: 1 }} />
            <span className="val">{fmtNum(c.drone_yaw_deg, 1, "°")}</span>
          </div>

          <div className="coord-metric">
            <span className="label">Heading err</span>
            <GaugeBar value={Math.abs(c.heading_error_deg ?? 0)} max={180} colorClass={Math.abs(c.heading_error_deg ?? 0) < 30 ? "ok" : "warn"} />
            <span className="val">{fmtNum(c.heading_error_deg, 0, "°")}</span>
          </div>

          <div className="coord-metric">
            <span className="label">Latency</span>
            <GaugeBar value={c.telemetry_latency_ms ?? 0} max={500} colorClass={(c.telemetry_latency_ms ?? 0) < 100 ? "ok" : (c.telemetry_latency_ms ?? 0) < 300 ? "warn" : "crit"} />
            <span className="val">{fmtNum(c.telemetry_latency_ms, 0, " ms")}</span>
          </div>

          <div className="coord-metric" style={{ borderBottom: "none" }}>
            <span className="label">Mode</span>
            <span style={{ flex: 1 }} />
            <span className="val" style={{ color: "var(--accent)", fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700 }}>{c.mode}</span>
          </div>
        </div>
      ) : (
        <div>
          {/* Separation trend badge — backend-driven */}
          <TrendBadge trend={c.separation_trend} predictedSep={c.predicted_separation_m} />

          <div className="coord-metric">
            <span className="label">Separation</span>
            <GaugeBar value={c.separation_m} max={sepMax} colorClass={sepColor} />
            <span className="val">
              {fmtNum(c.separation_m, 2, " m")}
              {c.target_separation_m != null && (
                <span style={{ color: "var(--text-2)", fontSize: 10 }}> / {fmtNum(c.target_separation_m, 1)}</span>
              )}
            </span>
          </div>

          <div className="coord-metric">
            <span className="label">Track error</span>
            <GaugeBar value={c.tracking_error_m ?? 0} max={4.0} colorClass={trackColor} />
            <span className="val" style={{ color: trackColor === "ok" ? "var(--ok)" : trackColor === "warn" ? "var(--warn)" : "var(--crit)" }}>
              {fmtNum(c.tracking_error_m, 2, " m")}
            </span>
          </div>

          <div className="coord-metric">
            <span className="label">Heading err</span>
            <GaugeBar value={Math.abs(c.heading_error_deg ?? 0)} max={180} colorClass={Math.abs(c.heading_error_deg ?? 0) < 30 ? "ok" : "warn"} />
            <span className="val">{fmtNum(c.heading_error_deg, 0, "°")}</span>
          </div>

          <div className="coord-metric">
            <span className="label">Latency</span>
            <GaugeBar value={c.telemetry_latency_ms ?? 0} max={500} colorClass={(c.telemetry_latency_ms ?? 0) < 100 ? "ok" : (c.telemetry_latency_ms ?? 0) < 300 ? "warn" : "crit"} />
            <span className="val">{fmtNum(c.telemetry_latency_ms, 0, " ms")}</span>
          </div>

          <div className="coord-metric" style={{ borderBottom: "none" }}>
            <span className="label">Mode</span>
            <span style={{ flex: 1 }} />
            <span className="val" style={{ color: "var(--text-1)", fontFamily: "var(--mono)", fontSize: 11 }}>{c.mode}</span>
          </div>

          {/* Separation sparkline — uses real WebSocket history data */}
          <SeparationSparkline targetSep={c.target_separation_m} />
        </div>
      )}

      <div style={{ marginTop: 8 }}>
        <LatencyPanel />
      </div>
    </div>
  );
}
