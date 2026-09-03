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
      <div>
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
      </div>

      <div style={{ marginTop: 8 }}>
        <LatencyPanel />
      </div>
    </div>
  );
}
