import { useMissionStore } from "@/stores/missionStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { healthDotClass, robotLabel } from "@/utils/format";

export default function HealthPanel() {
  const health = useMissionStore((s) => s.systemHealth);
  const wsStatus = useConnectionStore((s) => s.wsStatus);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span className="status-pill">
        <span className={`dot ${healthDotClass(health.overall)}`} />
        SYSTEM {health.overall}
      </span>
      {Object.entries(health.robots).map(([id, h]) => (
        <span key={id} className="status-pill">
          <span className={`dot ${healthDotClass(h)}`} />
          {robotLabel(id)}
        </span>
      ))}
      <span className="status-pill" title="Gateway WebSocket connection">
        <span className={`dot ${wsStatus === "OPEN" ? "ok" : wsStatus === "CONNECTING" ? "warn" : "crit"}`} />
        LINK {wsStatus}
      </span>
    </div>
  );
}
