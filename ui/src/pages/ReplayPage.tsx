import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/services/api";
import type { ExperimentSummary } from "@/types/experiment";
import type { RobotState } from "@/types/robot";
import type { CoordinationState } from "@/types/coordination";
import { LocalFrameMap } from "@/components/MissionMap";
import { fmtDuration } from "@/utils/format";

interface TelemetryRow {
  robot_id: string;
  timestamp_ms: number;
  state_json: string;
}

const SPEEDS = [0.5, 1, 2, 4];

export default function ReplayPage() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryRow[]>([]);
  const [coordSamples, setCoordSamples] = useState<{ timestamp_ms: number; state_json: string }[]>([]);
  const [cursorMs, setCursorMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);

  useEffect(() => {
    api.listExperiments().then(setExperiments).catch(() => setExperiments([]));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setPlaying(false);
    Promise.all([api.getExperimentTelemetryAll(selectedId), api.getExperimentCoordination(selectedId)]).then(
      ([tel, coord]) => {
        setTelemetry(tel);
        setCoordSamples(coord);
        setCursorMs(tel[0]?.timestamp_ms ?? 0);
      }
    );
  }, [selectedId]);

  const { startMs, endMs } = useMemo(() => {
    if (telemetry.length === 0) return { startMs: 0, endMs: 1 };
    const timestamps = telemetry.map((t) => t.timestamp_ms);
    return { startMs: Math.min(...timestamps), endMs: Math.max(...timestamps) };
  }, [telemetry]);

  useEffect(() => {
    if (!playing) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      lastTickRef.current = null;
      return;
    }
    function tick(now: number) {
      if (lastTickRef.current !== null) {
        const deltaMs = (now - lastTickRef.current) * speed;
        setCursorMs((c) => {
          const next = c + deltaMs;
          return next > endMs ? startMs : next;
        });
      }
      lastTickRef.current = now;
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, speed, startMs, endMs]);

  // Nearest-sample-at-or-before-cursor per robot, and for coordination.
  const robotsAtCursor: RobotState[] = useMemo(() => {
    const byRobot = new Map<string, TelemetryRow>();
    for (const row of telemetry) {
      if (row.timestamp_ms > cursorMs) continue;
      const existing = byRobot.get(row.robot_id);
      if (!existing || row.timestamp_ms > existing.timestamp_ms) byRobot.set(row.robot_id, row);
    }
    return Array.from(byRobot.values()).map((row) => JSON.parse(row.state_json) as RobotState);
  }, [telemetry, cursorMs]);

  const coordinationAtCursor: CoordinationState = useMemo(() => {
    let best: { timestamp_ms: number; state_json: string } | null = null;
    for (const row of coordSamples) {
      if (row.timestamp_ms > cursorMs) continue;
      if (!best || row.timestamp_ms > best.timestamp_ms) best = row;
    }
    return best
      ? JSON.parse(best.state_json)
      : {
          leader_id: null,
          follower_id: null,
          mode: "IDLE",
          separation_m: 0,
          target_separation_m: null,
          heading_error_deg: null,
          tracking_error_m: null,
          relative_velocity_mps: null,
          telemetry_latency_ms: null,
          state: "IDLE",
          updated_at_ms: 0,
        };
  }, [coordSamples, cursorMs]);

  return (
    <div className="page-content">
      <h2 style={{ marginTop: 0 }}>Mission Replay</h2>
      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 16 }}>
        <div className="panel" style={{ maxHeight: 500, overflowY: "auto" }}>
          <div className="panel-title">Experiments</div>
          {experiments.map((exp) => (
            <div
              key={exp.id}
              onClick={() => setSelectedId(exp.id)}
              style={{
                padding: "8px 10px",
                borderRadius: 6,
                cursor: "pointer",
                marginBottom: 4,
                background: selectedId === exp.id ? "var(--bg-3)" : "transparent",
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 12 }}>{exp.name ?? exp.id}</div>
            </div>
          ))}
        </div>

        <div>
          <div className="panel" style={{ height: 420 }}>
            <LocalFrameMap robots={robotsAtCursor} coordination={coordinationAtCursor} />
          </div>

          {telemetry.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <input
                type="range"
                min={startMs}
                max={endMs}
                value={cursorMs}
                onChange={(e) => setCursorMs(Number(e.target.value))}
                style={{ width: "100%" }}
              />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
                <div style={{ display: "flex", gap: 6 }}>
                  <button onClick={() => setPlaying((p) => !p)}>{playing ? "PAUSE" : "PLAY"}</button>
                  {SPEEDS.map((s) => (
                    <button key={s} className={speed === s ? "primary" : ""} onClick={() => setSpeed(s)}>
                      {s}x
                    </button>
                  ))}
                </div>
                <span className="mono" style={{ fontSize: 12 }}>
                  {fmtDuration((cursorMs - startMs) / 1000)} / {fmtDuration((endMs - startMs) / 1000)}
                </span>
              </div>
            </div>
          )}
          {selectedId && telemetry.length === 0 && <div className="empty-state">No telemetry recorded for this experiment.</div>}
        </div>
      </div>
    </div>
  );
}
