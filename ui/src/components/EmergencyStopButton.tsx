import { useState } from "react";
import { api } from "@/services/api";
import { useMissionStore } from "@/stores/missionStore";

export default function EmergencyStopButton() {
  const mission = useMissionStore((s) => s.mission);
  const [busy, setBusy] = useState(false);
  const isEmergency = mission.state === "EMERGENCY";

  async function trigger() {
    if (!confirm("Trigger EMERGENCY STOP? This immediately halts both robots.")) return;
    setBusy(true);
    try {
      await api.emergencyStop("operator_ui");
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    setBusy(true);
    try {
      await api.clearEmergency();
    } finally {
      setBusy(false);
    }
  }

  if (isEmergency) {
    return (
      <button className="emergency active" onClick={clear} disabled={busy}>
        CLEAR EMERGENCY STOP
      </button>
    );
  }

  return (
    <button className="emergency" onClick={trigger} disabled={busy}>
      EMERGENCY STOP
    </button>
  );
}
