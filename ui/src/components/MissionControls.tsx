import { useEffect, useRef, useState } from "react";
import { api } from "@/services/api";
import { useMissionStore } from "@/stores/missionStore";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { robotLabel } from "@/utils/format";
import EmergencyStopButton from "./EmergencyStopButton";

function ElapsedTimer({ startedAtMs }: { startedAtMs: number | null }) {
  const [elapsed, setElapsed] = useState("—");
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!startedAtMs) { setElapsed("—"); return; }
    function update() {
      const s = Math.floor((Date.now() - startedAtMs!) / 1000);
      const mm = String(Math.floor(s / 60)).padStart(2, "0");
      const ss = String(s % 60).padStart(2, "0");
      setElapsed(`${mm}:${ss}`);
      rafRef.current = requestAnimationFrame(update);
    }
    rafRef.current = requestAnimationFrame(update);
    return () => cancelAnimationFrame(rafRef.current);
  }, [startedAtMs]);

  return (
    <div className="mission-elapsed" title="Mission elapsed time">{elapsed}</div>
  );
}

const MISSION_STATE_COLORS: Record<string, string> = {
  DISCONNECTED: "var(--text-2)",
  READY: "var(--accent)",
  ARMED: "var(--warn)",
  RUNNING: "var(--ok)",
  PAUSED: "var(--warn)",
  DEGRADED: "var(--warn)",
  EMERGENCY: "var(--crit)",
  STOPPED: "var(--text-2)",
  COMPLETED: "var(--ok)",
};

export default function MissionControls() {
  const mission = useMissionStore((s) => s.mission);
  const robots = useRobotStore((s) => s.robots);
  const coordination = useCoordinationStore((s) => s.coordination);
  const [leaderId, setLeaderId] = useState<string>(coordination.leader_id ?? "");
  const [followerId, setFollowerId] = useState<string>(coordination.follower_id ?? "");
  const [recording, setRecording] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const robotIds = Object.keys(robots);
  const canStart = leaderId && followerId && leaderId !== followerId && !busy;
  const isRunning = mission.state === "RUNNING";
  const isPaused = mission.state === "PAUSED";
  const canControl = isRunning || isPaused;
  const missionColor = MISSION_STATE_COLORS[mission.state] ?? "var(--text-2)";

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function switchRoles() {
    if (!leaderId || !followerId) return;
    await run(() => api.setRoles(followerId, leaderId));
    const tmp = leaderId;
    setLeaderId(followerId);
    setFollowerId(tmp);
  }

  return (
    <div className="controls-bar">
      {/* Left: mission controls */}
      <div className="controls-left">
        {/* Mission state indicator */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <span style={{
            fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            letterSpacing: "0.07em", color: "var(--text-2)"
          }}>State</span>
          <span style={{ fontSize: 11, fontWeight: 800, color: missionColor, letterSpacing: "0.04em", fontFamily: "var(--mono)" }}>
            {mission.state}
          </span>
        </div>

        <div style={{ width: 1, height: 28, background: "var(--border)", flexShrink: 0 }} />

        {/* Role selectors — only when not running */}
        {!canControl && (
          <>
            <div className="role-selector-group">
              <span className="role-selector-label">Leader</span>
              <select value={leaderId} onChange={(e) => setLeaderId(e.target.value)} disabled={busy} id="select-leader">
                <option value="">Select…</option>
                {robotIds.map((id) => (
                  <option key={id} value={id} disabled={id === followerId}>{robotLabel(id)}</option>
                ))}
              </select>
            </div>
            <div style={{ color: "var(--text-2)", fontSize: 16 }}>→</div>
            <div className="role-selector-group">
              <span className="role-selector-label">Follower</span>
              <select value={followerId} onChange={(e) => setFollowerId(e.target.value)} disabled={busy} id="select-follower">
                <option value="">Select…</option>
                {robotIds.map((id) => (
                  <option key={id} value={id} disabled={id === leaderId}>{robotLabel(id)}</option>
                ))}
              </select>
            </div>

            <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--text-1)", cursor: "pointer", userSelect: "none" }}>
              <input type="checkbox" checked={recording} onChange={(e) => setRecording(e.target.checked)} />
              Record
            </label>
          </>
        )}

        {/* Elapsed timer when running */}
        {canControl && <ElapsedTimer startedAtMs={mission.started_at_ms ?? null} />}

        {/* Action buttons */}
        {!canControl && (
          <button
            className="primary"
            disabled={!canStart}
            onClick={() => run(() => api.startMission({ leader_id: leaderId, follower_id: followerId, recording }))}
            id="btn-start-mission"
          >
            ▶ START
          </button>
        )}
        {isRunning && (
          <button disabled={busy} onClick={() => run(() => api.pauseMission())} id="btn-pause-mission">
            ⏸ PAUSE
          </button>
        )}
        {isPaused && (
          <button className="primary" disabled={busy} onClick={() => run(() => api.resumeMission())} id="btn-resume-mission">
            ▶ RESUME
          </button>
        )}
        {canControl && (
          <button disabled={busy} onClick={() => run(() => api.stopMission())} id="btn-stop-mission">
            ⏹ STOP
          </button>
        )}
        {canControl && (
          <button disabled={busy} onClick={switchRoles} title="Swap leader and follower roles" id="btn-switch-roles">
            ⇄ ROLES
          </button>
        )}

        {error && (
          <span style={{ color: "var(--crit)", fontSize: 11, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            ⚠ {error}
          </span>
        )}
      </div>

      {/* Right: recording indicator + mission id + E-stop */}
      <div className="controls-right">
        {mission.recording && mission.experiment_id && (
          <div className="recording-indicator">
            <span className="rec-dot" />
            <span style={{ fontFamily: "var(--mono)", fontSize: 10 }}>REC · {mission.experiment_id.slice(0, 8)}</span>
          </div>
        )}
        {mission.mission_id && (
          <span style={{ fontSize: 10, color: "var(--text-2)", fontFamily: "var(--mono)" }}>
            {mission.mission_id}
          </span>
        )}
        <EmergencyStopButton />
      </div>
    </div>
  );
}
