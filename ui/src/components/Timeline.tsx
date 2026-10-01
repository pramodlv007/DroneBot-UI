import { useState, useMemo } from "react";
import { useEventStore } from "@/stores/eventStore";
import { fmtTime } from "@/utils/format";

const SEV_ICON: Record<string, string> = {
  INFO: "ℹ",
  WARNING: "⚠",
  CRITICAL: "🔴",
};

export default function Timeline() {
  const events = useEventStore((s) => s.events);
  const [filter, setFilter] = useState<"ALL" | "WARN" | "CRIT">("ALL");

  const filteredEvents = useMemo(() => {
    let list = [...events].reverse();
    if (filter === "WARN") {
      list = list.filter((e) => e.severity === "WARNING" || e.severity === "CRITICAL");
    } else if (filter === "CRIT") {
      list = list.filter((e) => e.severity === "CRITICAL");
    }
    return list;
  }, [events, filter]);

  return (
    <div className="panel timeline-panel">
      {/* Sleek header with event count and filter pills */}
      <div className="panel-title-row" style={{ marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              flexShrink: 0,
              background: events.length > 0 ? "var(--ok)" : "var(--unknown)",
              boxShadow: events.length > 0 ? "0 0 6px var(--ok-glow)" : "none",
            }}
          />
          <div className="panel-title" style={{ margin: 0, fontSize: 10, letterSpacing: "0.1em" }}>
            Event Log
          </div>
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: "1px 6px",
              borderRadius: 99,
              background: "var(--bg-3)",
              color: "var(--text-1)",
              border: "1px solid var(--border)",
              fontFamily: "var(--mono)",
            }}
          >
            {events.length}
          </span>
        </div>

        {/* Filter buttons */}
        <div style={{ display: "flex", gap: 2, background: "var(--bg-3)", padding: 2, borderRadius: 5, border: "1px solid var(--border)" }}>
          <button
            onClick={() => setFilter("ALL")}
            style={{
              padding: "1px 6px",
              fontSize: 8.5,
              height: 18,
              borderRadius: 3,
              border: "none",
              background: filter === "ALL" ? "var(--bg-1)" : "transparent",
              color: filter === "ALL" ? "var(--accent)" : "var(--text-2)",
              fontWeight: filter === "ALL" ? 700 : 500,
              boxShadow: filter === "ALL" ? "0 1px 2px rgba(0,0,0,0.08)" : "none",
            }}
          >
            ALL
          </button>
          <button
            onClick={() => setFilter("WARN")}
            style={{
              padding: "1px 6px",
              fontSize: 8.5,
              height: 18,
              borderRadius: 3,
              border: "none",
              background: filter === "WARN" ? "var(--bg-1)" : "transparent",
              color: filter === "WARN" ? "var(--warn)" : "var(--text-2)",
              fontWeight: filter === "WARN" ? 700 : 500,
              boxShadow: filter === "WARN" ? "0 1px 2px rgba(0,0,0,0.08)" : "none",
            }}
          >
            WARN+
          </button>
          <button
            onClick={() => setFilter("CRIT")}
            style={{
              padding: "1px 6px",
              fontSize: 8.5,
              height: 18,
              borderRadius: 3,
              border: "none",
              background: filter === "CRIT" ? "var(--bg-1)" : "transparent",
              color: filter === "CRIT" ? "var(--crit)" : "var(--text-2)",
              fontWeight: filter === "CRIT" ? 700 : 500,
              boxShadow: filter === "CRIT" ? "0 1px 2px rgba(0,0,0,0.08)" : "none",
            }}
          >
            CRIT
          </button>
        </div>
      </div>

      {/* Scrollable event list */}
      <div className="scroll-list">
        {filteredEvents.length === 0 && (
          <div className="empty-state" style={{ padding: "10px 4px", fontSize: 10 }}>
            {events.length === 0 ? "No events yet — connect a robot to start" : "No events matching filter"}
          </div>
        )}
        {filteredEvents.map((e, i) => (
          <div key={`${e.timestamp_ms}-${i}`} className="event-row" title={`${fmtTime(e.timestamp_ms)} [${e.severity}] ${e.message || e.type}`}>
            <span className="ts">{fmtTime(e.timestamp_ms)}</span>
            <span className={`badge ${e.severity}`} style={{ fontSize: 8.5, padding: "1px 5px", flexShrink: 0 }}>
              {SEV_ICON[e.severity] ?? ""} {e.severity}
            </span>
            <span className="event-msg">{e.message || e.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
