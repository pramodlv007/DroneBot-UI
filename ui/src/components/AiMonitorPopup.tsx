/**
 * AiMonitorPopup — a draggable floating panel wrapping the same real,
 * live AI monitor feed as the full "AI Monitor" tab (shared polling via
 * aiMonitorStore, see there), reachable from any tab instead of only the
 * dedicated one. This exists because the AI Monitor's warnings/alerts
 * were otherwise invisible to an operator looking at the map or robot
 * cards — the exact blind spot the AI is supposed to help with.
 */
import { useEffect, useRef, useState } from "react";
import { useAiMonitorStore } from "@/stores/aiMonitorStore";
import AiMonitorFeed from "./AiMonitorFeed";

const DEFAULT_POS = { right: 20, bottom: 20 };
const PANEL_WIDTH = 360;
const PANEL_MAX_HEIGHT = 480;

function statusColor(status: string | undefined) {
  if (status === "CRITICAL") return "var(--crit)";
  if (status === "WARNING") return "var(--warn)";
  return "var(--ok)";
}

export default function AiMonitorPopup() {
  const [open, setOpen] = useState(false);
  // Drag offset from the default bottom-right anchor. null until the user
  // actually drags it, so it doesn't jump position on first render.
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number } | null>(null);
  const dragState = useRef<{ startX: number; startY: number; baseX: number; baseY: number } | null>(null);

  const { feed, loading, error, acquire, release, pollNow, clearFeed } = useAiMonitorStore();
  const latestStatus = feed[0]?.overall_status;

  useEffect(() => {
    if (!open) return;
    acquire();
    return () => release();
  }, [open, acquire, release]);

  function onDragStart(e: React.MouseEvent) {
    dragState.current = {
      startX: e.clientX,
      startY: e.clientY,
      baseX: dragOffset?.x ?? 0,
      baseY: dragOffset?.y ?? 0,
    };
    window.addEventListener("mousemove", onDragMove);
    window.addEventListener("mouseup", onDragEnd);
  }

  function onDragMove(e: MouseEvent) {
    const s = dragState.current;
    if (!s) return;
    setDragOffset({ x: s.baseX + (e.clientX - s.startX), y: s.baseY + (e.clientY - s.startY) });
  }

  function onDragEnd() {
    dragState.current = null;
    window.removeEventListener("mousemove", onDragMove);
    window.removeEventListener("mouseup", onDragEnd);
  }

  // Clean up any lingering listeners if the popup unmounts mid-drag.
  useEffect(() => () => {
    window.removeEventListener("mousemove", onDragMove);
    window.removeEventListener("mouseup", onDragEnd);
  }, []);

  const style: React.CSSProperties = open
    ? {
        position: "fixed",
        right: DEFAULT_POS.right - (dragOffset?.x ?? 0),
        bottom: DEFAULT_POS.bottom - (dragOffset?.y ?? 0),
        width: PANEL_WIDTH,
        maxHeight: PANEL_MAX_HEIGHT,
        zIndex: 200,
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-2)",
        border: "1px solid var(--border-strong)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
        overflow: "hidden",
      }
    : {
        position: "fixed",
        right: DEFAULT_POS.right,
        bottom: DEFAULT_POS.bottom,
        zIndex: 200,
      };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="Open AI Mission Monitor"
        style={{
          ...style,
          width: 48, height: 48, borderRadius: "50%",
          background: "var(--bg-2)", border: `1.5px solid ${statusColor(latestStatus)}`,
          boxShadow: `0 0 16px ${statusColor(latestStatus)}55`,
          fontSize: 20, display: "flex", alignItems: "center", justifyContent: "center",
          cursor: "pointer",
        }}
      >
        🤖
      </button>
    );
  }

  return (
    <div style={style}>
      <div
        onMouseDown={onDragStart}
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "8px 10px", cursor: "grab", background: "var(--bg-3)",
          borderBottom: "1px solid var(--border)", flexShrink: 0, userSelect: "none",
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1)" }}>🤖 AI Monitor</span>
        <button
          onClick={() => setOpen(false)}
          title="Close"
          style={{ padding: "2px 8px", fontSize: 11, background: "transparent", border: "none", color: "var(--text-2)" }}
        >
          ✕
        </button>
      </div>
      <div style={{ overflowY: "auto", flex: 1 }}>
        <AiMonitorFeed feed={feed} loading={loading} error={error} onRetry={pollNow} onClear={clearFeed} maxVisible={6} />
      </div>
    </div>
  );
}
