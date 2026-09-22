import { useState } from "react";
import { api } from "@/services/api";
import { useMissionStore } from "@/stores/missionStore";

export default function EmergencyStopButton() {
  const mission = useMissionStore(s => s.mission);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const emergencyActive = useMissionStore(s => s.emergencyActive);
  const isEmergency = emergencyActive || mission.state === "EMERGENCY";

  async function act() {
    if (!isEmergency && !confirm("Trigger EMERGENCY STOP? This requests an immediate stop for all connected robots.")) return;
    setBusy(true);
    setError(null);
    try {
      if (isEmergency) {
        useMissionStore.getState().setMission(await api.clearEmergency());
        useMissionStore.getState().setEmergencyActive(false);
      } else {
        const result = await api.emergencyStop("operator_ui");
        useMissionStore.getState().setMission(result.mission);
        useMissionStore.getState().setEmergencyActive(result.emergency.active);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed. Try again.");
    } finally { setBusy(false); }
  }
  return <div className="emergency-control">
    <button className={`emergency ${isEmergency ? "active" : ""}`} onClick={act} disabled={busy}>
      {busy ? "Sending request…" : isEmergency ? "Clear emergency stop" : "Emergency stop"}
    </button>
    {error && <div className="inline-error" role="alert">{error}</div>}
  </div>;
}
