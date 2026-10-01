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

const ACTION_BG: Record<string, string> = {
  CONTINUE: "rgba(46,219,122,0.08)",
  SLOW_DOWN: "rgba(255,170,42,0.08)",
  PAUSE: "rgba(255,170,42,0.08)",
  STOP: "rgba(255,59,92,0.08)",
  CHECK_GPS: "rgba(255,170,42,0.08)",
  CHECK_COMMUNICATION: "rgba(255,170,42,0.08)",
  RETURN_TO_SAFE_STATE: "rgba(255,59,92,0.08)",
};

export default function SupervisorPanel() {
  const rec = useMissionStore((s) => s.supervisor);

  return (
    <div className="panel supervisor-panel" style={{ overflowY: "auto", minHeight: 0 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 8,
          background: "linear-gradient(135deg, rgba(77,159,255,0.2), rgba(77,159,255,0.05))",
          border: "1px solid rgba(77,159,255,0.2)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, flexShrink: 0,
        }}>🤖</div>
        <div>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-2)" }}>
            AI Supervisor
          </div>
          <div style={{ fontSize: 9, color: "var(--text-3)", fontFamily: "var(--mono)" }}>
            Mission intelligence
          </div>
        </div>
      </div>

      {!rec ? (
        <div className="empty-state" style={{ padding: "20px 0" }}>
          <div style={{ fontSize: 24, marginBottom: 8 }}>🤖</div>
          <div style={{ fontSize: 11 }}>Waiting for first supervisor cycle…</div>
        </div>
      ) : (
        <>
          {/* Status + Recommendation row */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
            <span className={`badge ${rec.status}`}>{rec.status}</span>
            <span style={{
              fontSize: 10, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase",
              color: ACTION_COLOR[rec.recommended_action] ?? "var(--text-1)",
              background: ACTION_BG[rec.recommended_action] ?? "transparent",
              border: `1px solid ${ACTION_COLOR[rec.recommended_action] ?? "transparent"}30`,
              borderRadius: 99,
              padding: "3px 10px",
              fontFamily: "var(--mono)",
            }}>
              → {rec.recommended_action.replace(/_/g, " ")}
            </span>
          </div>

          {/* Confidence bar */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 9, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 700 }}>
                Confidence
              </span>
              <span style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--accent-bright)", fontWeight: 700 }}>
                {fmtNum(rec.confidence * 100, 0, "%")}
              </span>
            </div>
            <div className="confidence-bar-track">
              <div className="confidence-bar-fill" style={{ width: `${(rec.confidence * 100).toFixed(0)}%` }} />
            </div>
          </div>

          {/* Issue */}
          {rec.detected_issue && (
            <div style={{
              fontSize: 10.5, color: "var(--warn)", marginBottom: 8,
              padding: "6px 10px",
              background: "rgba(255,170,42,0.06)",
              borderRadius: 8,
              border: "1px solid rgba(255,170,42,0.2)",
            }}>
              ⚠ {rec.detected_issue}
            </div>
          )}

          {/* Summary */}
          {rec.summary && (
            <div className="supervisor-summary">{rec.summary}</div>
          )}

          {/* Footer */}
          <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--text-3)", fontFamily: "var(--mono)" }}>
            <span>{rec.provider}{rec.latency_ms != null && ` · ${fmtNum(rec.latency_ms, 0, " ms")}`}</span>
            <span>{fmtTime(rec.timestamp_ms)}</span>
          </div>
        </>
      )}
    </div>
  );
}
