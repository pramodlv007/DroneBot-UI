import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/services/api";
import { Link } from "react-router-dom";
import { useAsyncData } from "@/hooks/useAsyncData";
import LoadState from "@/components/LoadState";
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
  const list = useAsyncData(api.listExperiments);
  const experiments = list.data ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [cursorMs, setCursorMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number | null>(null);

  const loadRecording = useCallback(async () => {
    const [telemetry, coordination] = await Promise.all([
      api.getExperimentTelemetryAll(selectedId!), api.getExperimentCoordination(selectedId!),
    ]);
    return { telemetry, coordination };
  }, [selectedId]);
  const recording = useAsyncData(selectedId ? loadRecording : null);
  const telemetry = recording.data?.telemetry ?? [];
  const coordSamples = recording.data?.coordination ?? [];

  useEffect(() => { setPlaying(false); setCursorMs(0); }, [selectedId]);
  useEffect(() => {
    if (recording.data?.telemetry.length) setCursorMs(recording.data.telemetry.reduce((min, row) => Math.min(min, row.timestamp_ms), Infinity));
  }, [recording.data]);

  const { startMs, endMs } = useMemo(() => {
    if (telemetry.length === 0) return { startMs: 0, endMs: 1 };
    return telemetry.reduce((range, row) => ({
      startMs: Math.min(range.startMs, row.timestamp_ms), endMs: Math.max(range.endMs, row.timestamp_ms),
    }), { startMs: Infinity, endMs: -Infinity });
  }, [telemetry]);

  useEffect(() => {
    if (!playing || !recording.data || telemetry.length === 0) {
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
      lastTickRef.current = null;
    };
  }, [playing, speed, startMs, endMs, recording.data]);

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
      <div className="page-heading"><div><div className="eyebrow">Review a recorded run</div><h1>Mission replay</h1><p>Scrub the timeline or play back robot movement at your own pace.</p></div></div>
      <div className="review-layout">
        <div className="panel review-sidebar">
          <div className="panel-title">Experiments</div>
          <LoadState {...list} />
          {!list.loading && !list.error && experiments.length === 0 && <div className="empty-state"><p>No recordings yet. Start a mission with recording enabled.</p><Link to="/?view=mission">Open mission control</Link></div>}
          {experiments.map((exp) => (
            <button className="recording-choice" aria-pressed={selectedId === exp.id}
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
            </button>
          ))}
        </div>

        <div className="review-detail">
          <LoadState {...recording} />
          {!selectedId && <div className="empty-state panel"><h2>Choose a recording</h2><p>Select an experiment to explore its timeline.</p></div>}
          {selectedId && !recording.loading && !recording.error && telemetry.length > 0 && <div className="panel replay-map">
            <LocalFrameMap robots={robotsAtCursor} coordination={coordinationAtCursor} />
          </div>}

          {telemetry.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <input
                type="range"
                step={100}
                aria-label="Replay position"
                aria-valuetext={fmtDuration((cursorMs - startMs) / 1000)}
                min={startMs}
                max={endMs}
                value={cursorMs}
                onChange={(e) => setCursorMs(Number(e.target.value))}
                style={{ width: "100%" }}
              />
              <div className="replay-controls">
                <div style={{ display: "flex", gap: 6 }}>
                  <button onClick={() => setPlaying((p) => !p)}>{playing ? "PAUSE" : "PLAY"}</button>
                  {SPEEDS.map((s) => (
                    <button key={s} className={speed === s ? "primary" : ""} aria-pressed={speed === s} aria-label={`Playback speed ${s}×`} onClick={() => setSpeed(s)}>
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
          {selectedId && !recording.loading && !recording.error && telemetry.length === 0 && <div className="empty-state">No telemetry recorded for this experiment.</div>}
        </div>
      </div>
    </div>
  );
}
