import { useEffect, useState } from "react";
import { api } from "@/services/api";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import RobotCard from "./RobotCard";
import TelemetryHistoryPanel from "./TelemetryHistoryPanel";
import type { RegisteredRobot } from "@/types/robot";

// Robot cards render dynamically from GET /api/robots merged with live
// WebSocket state — the UI never hard-codes "exactly two robots" (§8).
export default function RobotsPanel() {
  const liveStates = useRobotStore((s) => s.robots);
  const coordination = useCoordinationStore((s) => s.coordination);
  const [registry, setRegistry] = useState<RegisteredRobot[]>([]);

  useEffect(() => {
    let mounted = true;
    async function refresh() {
      try {
        const robots = await api.listRobots();
        if (mounted) setRegistry(robots);
      } catch {
        /* transient — next poll will retry */
      }
    }
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const connectedCount = registry.filter((r) => r.connected).length;

  return (
    <div className="panel robots-panel">
      <div className="panel-title-row">
        <div className="panel-title" style={{ margin: 0 }}>Robots</div>
        <span className="muted-label">{connectedCount} of {registry.length} connected</span>
      </div>

      <div className="robots-scroll-container">
        {registry.length === 0 && (
          <div className="empty-state" style={{ fontSize: 11 }}>No robots registered</div>
        )}
        {registry.map((robot) => (
          <RobotCard
            key={robot.robotId}
            robot={{ ...robot, state: liveStates[robot.robotId] ?? robot.state }}
            isLeader={coordination.leader_id === robot.robotId}
            isFollower={coordination.follower_id === robot.robotId}
          />
        ))}

        {/* Sparkline history below the cards */}
        <details className="quiet-details"><summary>Telemetry history</summary><TelemetryHistoryPanel /></details>
      </div>
    </div>
  );
}
