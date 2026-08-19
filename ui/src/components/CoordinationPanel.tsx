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

export default function CoordinationPanel() {
  const c = useCoordinationStore((s) => s.coordination);

  return (
    <div className="panel coordination-panel">
      <div className="panel-title">Coordination</div>

      <div className="kv-row">
        <span className="label">Leader</span>
        <span className="value">{c.leader_id ? robotLabel(c.leader_id) : "—"}</span>
      </div>
      <div className="kv-row">
        <span className="label">Follower</span>
        <span className="value">{c.follower_id ? robotLabel(c.follower_id) : "—"}</span>
      </div>
      <div className="kv-row">
        <span className="label">Mode</span>
        <span className="value">{c.mode}</span>
      </div>
      <div className="kv-row">
        <span className="label">Tracking error</span>
        <span className="value">{fmtNum(c.tracking_error_m, 2, " m")}</span>
      </div>
      <div className="kv-row">
        <span className="label">Separation</span>
        <span className="value">
          {fmtNum(c.separation_m, 2, " m")}
          {c.target_separation_m !== null && <span style={{ color: "var(--text-2)" }}> / {fmtNum(c.target_separation_m, 1, " m")}</span>}
        </span>
      </div>
      <div className="kv-row">
        <span className="label">Heading error</span>
        <span className="value">{fmtNum(c.heading_error_deg, 0, "°")}</span>
      </div>
      <div className="kv-row">
        <span className="label">Latency</span>
        <span className="value">{fmtNum(c.telemetry_latency_ms, 0, " ms")}</span>
      </div>
      <div className="kv-row" style={{ border: "none" }}>
        <span className="label">State</span>
        <span className={`badge ${STATE_BADGE[c.state] ?? "UNKNOWN"}`}>{c.state}</span>
      </div>

      <div style={{ marginTop: 10 }}>
        <LatencyPanel />
      </div>
    </div>
  );
}
