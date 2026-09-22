import { useEffect, useState } from "react";
import { api } from "@/services/api";
import { useMissionStore } from "@/stores/missionStore";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { robotLabel, fmtDuration } from "@/utils/format";
import { isActiveMission, startBlockReason } from "@/utils/mission";
import type { MissionState } from "@/types/mission";
import EmergencyStopButton from "./EmergencyStopButton";

function ElapsedTimer({ startedAtMs }: { startedAtMs: number | null }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return <span className="mission-elapsed" title="Wall time since mission start, including pauses">
    {startedAtMs ? fmtDuration(Math.max(0, now - startedAtMs) / 1000) : "—"}
  </span>;
}

export default function MissionControls() {
  const mission = useMissionStore(s => s.mission);
  const robots = useRobotStore(s => s.robots);
  const coordination = useCoordinationStore(s => s.coordination);
  const online = useConnectionStore(s => s.wsStatus === "OPEN");
  const [leaderId, setLeaderId] = useState(coordination.leader_id ?? "");
  const [followerId, setFollowerId] = useState(coordination.follower_id ?? "");
  const [recording, setRecording] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const emergencyActive = useMissionStore(s => s.emergencyActive);
  const active = isActiveMission(mission.state) || emergencyActive;
  const canStop = ["RUNNING", "PAUSED", "DEGRADED", "EMERGENCY"].includes(mission.state);
  const canSwap = ["RUNNING", "PAUSED", "DEGRADED"].includes(mission.state);
  const blocked = startBlockReason(mission.state, online, leaderId, followerId, robots);

  useEffect(() => {
    if (coordination.leader_id) setLeaderId(coordination.leader_id);
    if (coordination.follower_id) setFollowerId(coordination.follower_id);
  }, [coordination.leader_id, coordination.follower_id]);

  async function run(label: string, action: () => Promise<unknown>) {
    setPending(label);
    setError(null);
    try { await action(); } catch (e) {
      setError(e instanceof Error ? e.message : "The request failed. Try again.");
    } finally { setPending(null); }
  }
  const updateMission = async (action: () => Promise<MissionState>) => {
    useMissionStore.getState().setMission(await action());
  };
  const disabled = !!pending || !online;

  return (
    <section className="mission-controls" aria-label="Mission controls" aria-busy={!!pending}>
      <div className="controls-bar">
        <div className="controls-left">
          <div className="mission-status"><span className="role-selector-label">Mission state</span>
            <strong className={`badge ${mission.state}`}>{mission.state}</strong>
          </div>
          {!active ? <>
            <div className="role-selector-group">
              <label className="role-selector-label" htmlFor="select-leader">Leader</label>
              <select id="select-leader" value={leaderId} onChange={e => setLeaderId(e.target.value)} disabled={disabled}>
                <option value="">Choose leader</option>
                {Object.values(robots).map(r => <option key={r.robot_id} value={r.robot_id} disabled={!r.connected || r.robot_id === followerId}>
                  {robotLabel(r.robot_id)}{r.connected ? "" : " · Offline"}
                </option>)}
              </select>
            </div>
            <div className="role-selector-group">
              <label className="role-selector-label" htmlFor="select-follower">Follower</label>
              <select id="select-follower" value={followerId} onChange={e => setFollowerId(e.target.value)} disabled={disabled}>
                <option value="">Choose follower</option>
                {Object.values(robots).map(r => <option key={r.robot_id} value={r.robot_id} disabled={!r.connected || r.robot_id === leaderId}>
                  {robotLabel(r.robot_id)}{r.connected ? "" : " · Offline"}
                </option>)}
              </select>
            </div>
            <label className="record-option"><input type="checkbox" checked={recording} disabled={disabled} onChange={e => setRecording(e.target.checked)} /> Record experiment</label>
            <button className="primary" disabled={disabled || !!blocked} aria-describedby="mission-feedback" id="btn-start-mission"
              onClick={() => run("Starting mission…", () => updateMission(() => api.startMission({ leader_id: leaderId, follower_id: followerId, recording })))}>Start mission</button>
          </> : <>
            <span className="active-roles">{robotLabel(coordination.leader_id ?? "")} <span aria-label="leads">→</span> {robotLabel(coordination.follower_id ?? "")}</span>
            <ElapsedTimer startedAtMs={mission.started_at_ms} />
          </>}
          {mission.state === "RUNNING" && <button disabled={disabled} onClick={() => run("Pausing…", () => updateMission(api.pauseMission))}>Pause</button>}
          {mission.state === "PAUSED" && <button className="primary" disabled={disabled} onClick={() => run("Resuming…", () => updateMission(api.resumeMission))}>Resume</button>}
          {canStop && <button disabled={disabled} onClick={() => run("Stopping…", () => updateMission(api.stopMission))}>Stop mission</button>}
          {canSwap && <button disabled={disabled || !coordination.leader_id || !coordination.follower_id}
            onClick={() => run("Swapping roles…", async () => {
              const leader = coordination.follower_id!;
              const follower = coordination.leader_id!;
              await api.setRoles(leader, follower);
              setLeaderId(leader);
              setFollowerId(follower);
            })}>Swap roles</button>}
        </div>
        <div className="controls-right">
          {active && mission.recording && mission.experiment_id && <span className="recording-indicator"><span className="rec-dot" /> Recording</span>}
          <EmergencyStopButton />
        </div>
      </div>
      <div id="mission-feedback" className={`control-feedback ${error ? "error" : ""}`} role={error ? "alert" : "status"}>
        {error ?? pending ?? (emergencyActive ? "Emergency stop is active. Clear it when safe before starting another mission." : mission.state === "DEGRADED" ? "Tracking lost. Movement is suspended; check robot connections or stop the mission." :
          !active ? blocked ?? "Ready to start. Your selected roles will be used for this mission." :
          mission.state === "PAUSED" ? "Mission paused. Resume when ready, or stop to finish the recording." : `Mission ${mission.mission_id ?? ""}`)}
      </div>
    </section>
  );
}
