import { useEventStore } from "@/stores/eventStore";
import { fmtTime } from "@/utils/format";

const SEV_ICON: Record<string, string> = {
  INFO: "ℹ",
  WARNING: "⚠",
  CRITICAL: "🔴",
};

export default function Timeline() {
  const events = useEventStore((s) => s.events);
  const reversed = [...events].reverse();

  return (
    <div className="panel timeline-panel">
      <div className="panel-title">Event Log</div>
      <div className="scroll-list">
        {reversed.length === 0 && (
          <div className="empty-state" style={{ padding: 12, fontSize: 11 }}>
            No events yet — connect a robot to start
          </div>
        )}
        {reversed.map((e, i) => (
          <div key={`${e.timestamp_ms}-${i}`} className="event-row">
            <span className="ts">{fmtTime(e.timestamp_ms)}</span>
            <span className={`badge ${e.severity}`} style={{ fontSize: 9 }}>
              {SEV_ICON[e.severity] ?? ""} {e.severity}
            </span>
            <span className="event-msg">{e.message || e.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
