import { useMissionStore } from "@/stores/missionStore";
import { fmtNum, fmtTime } from "@/utils/format";

const ACTION_COLOR: Record<string, string> = {
  CONTINUE: "var(--ok)",
  SLOW_DOWN: "var(--warn)",
  PAUSE: "var(--warn)",
  STOP: "var(--crit)",
  CHECK_GPS: "var(--warn)",
  CHECK_COMMUNICATION: "var(--warn)",
  RETURN_TO_SAFE_STATE: "var(--crit)",
};

export default function SupervisorPanel() {
  const rec = useMissionStore((s) => s.supervisor);

  return (
    <div className="panel supervisor-panel">
      <div className="panel-title">AI Mission Supervisor</div>

      {!rec ? (
        <div className="empty-state" style={{ padding: 16 }}>
          <div style={{ fontSize: 18, marginBottom: 4 }}>🤖</div>
          Waiting for first supervisor cycle…
        </div>
      ) : (
        <>
          {/* Status + Recommendation */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <span className={`badge ${rec.status}`}>{rec.status}</span>
            <span style={{
              fontSize: 11, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase",
              color: ACTION_COLOR[rec.recommended_action] ?? "var(--text-1)",
              fontFamily: "var(--mono)",
            }}>
              {rec.recommended_action.replace(/_/g, " ")}
            </span>
          </div>

          {/* Confidence bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
            <span style={{ fontSize: 9.5, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.05em", flex: "none" }}>
              Confidence
            </span>
            <div className="confidence-bar-track">
              <div className="confidence-bar-fill" style={{ width: `${(rec.confidence * 100).toFixed(0)}%` }} />
            </div>
            <span style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--accent-bright)", minWidth: 28, textAlign: "right" }}>
              {fmtNum(rec.confidence * 100, 0, "%")}
            </span>
          </div>

          {/* Issue */}
          {rec.detected_issue && (
            <div style={{ fontSize: 11, color: "var(--warn)", marginBottom: 6, padding: "4px 8px", background: "var(--warn-dim)", borderRadius: 5, border: "1px solid rgba(255,180,58,0.15)" }}>
              ⚠ {rec.detected_issue}
            </div>
          )}

          {/* Summary */}
          {rec.summary && (
            <div className="supervisor-summary">{rec.summary}</div>
          )}

          {/* Footer */}
          <div style={{ marginTop: 8, display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "var(--text-2)" }}>
            <span>{rec.provider}{rec.latency_ms != null && ` · ${fmtNum(rec.latency_ms, 0, " ms")}`}</span>
            <span>{fmtTime(rec.timestamp_ms)}</span>
          </div>
        </>
      )}
    </div>
  );
}
