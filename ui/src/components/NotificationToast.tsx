/**
 * NotificationToast — floating toast notifications triggered by real backend
 * events via the eventStore. Watches for WARNING and CRITICAL events
 * (including PREDICTED_SEPARATION_WARNING) and displays them as slide-in
 * toasts at the top-right.
 *
 * - WARNING events: amber toast, auto-dismiss after 8s
 * - CRITICAL events: red toast, sticky until manually dismissed
 * - PREDICTED_SEPARATION_WARNING: special orange styling with prediction data
 *
 * This component does NOT create fake alerts — it only fires when the backend
 * emits a real event through gw.emit_event().
 */
import { useEffect, useRef, useState } from "react";
import { useEventStore } from "@/stores/eventStore";
import type { MissionEvent } from "@/types/mission";

interface Toast {
  id: number;
  event: MissionEvent;
  dismissedAt: number | null;
}

const MAX_TOASTS = 5;
const WARNING_DISMISS_MS = 8000;

function toastIcon(event: MissionEvent): string {
  if (event.type === "PREDICTED_SEPARATION_WARNING") return "🔮";
  if (event.severity === "CRITICAL") return "🚨";
  if (event.severity === "WARNING") return "⚠️";
  return "ℹ️";
}

function toastClass(event: MissionEvent): string {
  if (event.type === "PREDICTED_SEPARATION_WARNING") return "toast-prediction";
  if (event.severity === "CRITICAL") return "toast-critical";
  if (event.severity === "WARNING") return "toast-warning";
  return "toast-info";
}

export default function NotificationToast() {
  const events = useEventStore((s) => s.events);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(0);
  const lastEventCountRef = useRef(0);

  // Watch for new events
  useEffect(() => {
    if (events.length <= lastEventCountRef.current) {
      lastEventCountRef.current = events.length;
      return;
    }

    // Get only new events since last check
    const newEvents = events.slice(lastEventCountRef.current);
    lastEventCountRef.current = events.length;

    // Only toast WARNING and CRITICAL events
    const toastable = newEvents.filter(
      (e) => e.severity === "WARNING" || e.severity === "CRITICAL"
    );

    if (toastable.length === 0) return;

    setToasts((prev) => {
      const additions: Toast[] = toastable.map((event) => ({
        id: idRef.current++,
        event,
        dismissedAt: null,
      }));
      return [...prev, ...additions].slice(-MAX_TOASTS);
    });
  }, [events]);

  // Auto-dismiss WARNING toasts after 8s
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      setToasts((prev) =>
        prev.filter((t) => {
          if (t.event.severity === "CRITICAL") return true; // never auto-dismiss
          if (t.dismissedAt) return now - t.dismissedAt < 400; // keep during exit anim
          const age = now - t.event.timestamp_ms;
          if (age > WARNING_DISMISS_MS) {
            t.dismissedAt = now;
            return true; // will be removed next tick
          }
          return true;
        })
      );
    }, 500);
    return () => clearInterval(timer);
  }, []);

  const dismiss = (id: number) => {
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, dismissedAt: Date.now() } : t))
    );
    // Remove after exit animation
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 400);
  };

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container">
      {toasts.map((t) => {
        const exiting = t.dismissedAt != null;
        const time = new Date(t.event.timestamp_ms).toLocaleTimeString("en-US", {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });

        return (
          <div
            key={t.id}
            className={`toast-item ${toastClass(t.event)} ${exiting ? "toast-exit" : "toast-enter"}`}
          >
            <div className="toast-header">
              <span className="toast-icon">{toastIcon(t.event)}</span>
              <span className="toast-type">{t.event.type.replace(/_/g, " ")}</span>
              <span className="toast-time">{time}</span>
              <button className="toast-close" onClick={() => dismiss(t.id)} title="Dismiss">×</button>
            </div>
            <div className="toast-message">{t.event.message}</div>
            {/* Show prediction data if available */}
            {t.event.type === "PREDICTED_SEPARATION_WARNING" && t.event.metadata && (
              <div className="toast-meta">
                <span>Current: {(t.event.metadata.current_separation_m as number)?.toFixed(1)}m</span>
                <span>Predicted: {t.event.value?.toFixed(1)}m</span>
                <span>Trend: {t.event.metadata.separation_trend as string}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
