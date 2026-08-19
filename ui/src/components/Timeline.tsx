import { useEventStore } from "@/stores/eventStore";
import { fmtTime } from "@/utils/format";

export default function Timeline() {
  const events = useEventStore((s) => s.events);
  const reversed = [...events].reverse();

  return (
    <div className="panel timeline-panel">
      <div className="panel-title">Event Timeline</div>
      <div className="scroll-list">
        {reversed.length === 0 && <div className="empty-state">No events yet</div>}
        {reversed.map((e, i) => (
          <div key={`${e.timestamp_ms}-${i}`} className="event-row">
            <span className="ts">{fmtTime(e.timestamp_ms)}</span>
            <span className={`badge ${e.severity}`}>{e.severity}</span>
            <span>{e.message || e.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
