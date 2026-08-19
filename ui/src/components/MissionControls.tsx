import { useState } from "react";
import { api } from "@/services/api";
import { useMissionStore } from "@/stores/missionStore";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { robotLabel } from "@/utils/format";
import EmergencyStopButton from "./EmergencyStopButton";

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
    await run(() => api.setRoles(followerId, leaderId)); // swap
    setLeaderId(followerId);
    setFollowerId(leaderId);
  }

  return (
    <div className="controls-bar">
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {!canControl && (
          <>
            <select value={leaderId} onChange={(e) => setLeaderId(e.target.value)} disabled={busy}>
              <option value="">Leader…</option>
              {robotIds.map((id) => (
                <option key={id} value={id} disabled={id === followerId}>
                  {robotLabel(id)}
                </option>
              ))}
            </select>
            <select value={followerId} onChange={(e) => setFollowerId(e.target.value)} disabled={busy}>
              <option value="">Follower…</option>
              {robotIds.map((id) => (
                <option key={id} value={id} disabled={id === leaderId}>
                  {robotLabel(id)}
                </option>
              ))}
            </select>
            <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--text-1)" }}>
              <input type="checkbox" checked={recording} onChange={(e) => setRecording(e.target.checked)} />
              Record experiment
            </label>
          </>
        )}

        {!canControl && (
          <button className="primary" disabled={!canStart} onClick={() => run(() => api.startMission({ leader_id: leaderId, follower_id: followerId, recording }))}>
            START
          </button>
        )}
        {isRunning && (
          <button disabled={busy} onClick={() => run(() => api.pauseMission())}>
            PAUSE
          </button>
        )}
        {isPaused && (
          <button className="primary" disabled={busy} onClick={() => run(() => api.resumeMission())}>
            RESUME
          </button>
        )}
        {canControl && (
          <button disabled={busy} onClick={() => run(() => api.stopMission())}>
            STOP
          </button>
        )}
        {canControl && (
          <button disabled={busy} onClick={switchRoles} title="Switch leader/follower roles mid-mission">
            SWITCH ROLES
          </button>
        )}

        {error && <span style={{ color: "var(--crit)", fontSize: 11 }}>{error}</span>}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        {mission.recording && mission.experiment_id && (
          <span style={{ fontSize: 11, color: "var(--text-1)" }}>
            <span className="dot ok" style={{ display: "inline-block", marginRight: 5 }} />
            Recording {mission.experiment_id}
          </span>
        )}
        <span style={{ fontSize: 11, color: "var(--text-2)" }}>Mission: {mission.mission_id ?? "—"}</span>
        <EmergencyStopButton />
      </div>
    </div>
  );
}
