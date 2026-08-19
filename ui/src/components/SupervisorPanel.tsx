import { useMissionStore } from "@/stores/missionStore";
import { fmtNum, fmtTime } from "@/utils/format";

export default function SupervisorPanel() {
  const rec = useMissionStore((s) => s.supervisor);

  return (
    <div className="panel supervisor-panel">
      <div className="panel-title">AI Mission Supervisor</div>

      {!rec ? (
        <div className="empty-state">Waiting for first supervisor cycle…</div>
      ) : (
        <>
          <div className="kv-row">
            <span className="label">Status</span>
            <span className={`badge ${rec.status}`}>{rec.status}</span>
          </div>
          <div className="kv-row">
            <span className="label">Recommendation</span>
            <span className="value">{rec.recommended_action}</span>
          </div>
          <div className="kv-row">
            <span className="label">Confidence</span>
            <span className="value">{fmtNum(rec.confidence * 100, 0, "%")}</span>
          </div>
          {rec.detected_issue && (
            <div className="kv-row">
              <span className="label">Detected issue</span>
              <span className="value">{rec.detected_issue}</span>
            </div>
          )}
          <div className="kv-row" style={{ border: "none" }}>
            <span className="label">Provider</span>
            <span className="value">
              {rec.provider}
              {rec.latency_ms !== null && ` · ${fmtNum(rec.latency_ms, 0, " ms")}`}
            </span>
          </div>
          <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--text-1)", lineHeight: 1.5 }}>
            {rec.summary}
            {rec.reasoning_summary && (
              <div style={{ marginTop: 4, color: "var(--text-2)" }}>{rec.reasoning_summary}</div>
            )}
          </div>
          <div style={{ marginTop: 6, fontSize: 10, color: "var(--text-2)" }}>Last updated {fmtTime(rec.timestamp_ms)}</div>
        </>
      )}
    </div>
  );
}
