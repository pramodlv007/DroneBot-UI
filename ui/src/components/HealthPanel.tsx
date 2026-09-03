import { useMissionStore } from "@/stores/missionStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { healthDotClass } from "@/utils/format";

function RobotDot({ id, health }: { id: string; health: string }) {
  const short = id.replace(/_\d+$/, "").replace("drone", "🚁").replace("turtlebot", "🤖");
  return (
    <span className="status-pill" title={`${id}: ${health}`} style={{ padding: "3px 8px", gap: 5 }}>
      <span className={`dot ${healthDotClass(health)}`} />
      <span style={{ fontSize: 10 }}>{short}</span>
    </span>
  );
}

export default function HealthPanel() {
  const health = useMissionStore((s) => s.systemHealth);
  const wsStatus = useConnectionStore((s) => s.wsStatus);

  const wsClass = wsStatus === "OPEN" ? "ok" : wsStatus === "CONNECTING" ? "warn" : "crit";

  return (
    <div className="health-top">
      {/* Per-robot dots */}
      {Object.entries(health.robots).map(([id, h]) => (
        <RobotDot key={id} id={id} health={h} />
      ))}

      {/* Overall system health */}
      <span className="status-pill" style={{ padding: "3px 8px", gap: 5 }}>
        <span className={`dot ${healthDotClass(health.overall)}`} />
        <span style={{ fontSize: 10, letterSpacing: "0.04em" }}>SYS</span>
      </span>

      {/* WebSocket gateway link */}
      <span className="status-pill" title={`Gateway WebSocket: ${wsStatus}`} style={{ padding: "3px 8px", gap: 5 }}>
        <span className={`dot ${wsClass}`} />
        <span style={{ fontSize: 10 }}>GW</span>
      </span>
    </div>
  );
}
