import { useEffect, useState } from "react";
import { api } from "@/services/api";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import RobotCard from "./RobotCard";
import TelemetryHistoryPanel from "./TelemetryHistoryPanel";
import type { RegisteredRobot } from "@/types/robot";

export default function RobotsPanel() {
  const liveStates = useRobotStore((s) => s.robots);
  const coordination = useCoordinationStore((s) => s.coordination);
  const [registry, setRegistry] = useState<RegisteredRobot[]>([]);
  const [activeTab, setActiveTab] = useState<string>("all");

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
  const allOnline = connectedCount > 0 && connectedCount === registry.length;

  const displayedRobots =
    activeTab === "all"
      ? registry
      : registry.filter((r) => r.robotId === activeTab);

  return (
    <div className="panel robots-panel">
      {/* Header with Fleet status and Navigation Tabs */}
      <div className="panel-title-row" style={{ marginBottom: 8, flexShrink: 0, gap: 6, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              flexShrink: 0,
              background: connectedCount > 0 ? "var(--ok)" : "var(--unknown)",
              boxShadow: connectedCount > 0 ? "0 0 6px var(--ok-glow)" : "none",
            }}
          />
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-1)" }}>
            Fleet
          </div>
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              color: allOnline ? "var(--ok)" : connectedCount > 0 ? "var(--warn)" : "var(--text-2)",
              background: allOnline ? "var(--ok-dim)" : connectedCount > 0 ? "var(--warn-dim)" : "var(--unknown-dim)",
              border: `1px solid ${allOnline ? "rgba(5,150,105,0.25)" : connectedCount > 0 ? "rgba(217,119,6,0.25)" : "var(--border)"}`,
              padding: "1px 6px",
              borderRadius: 99,
              letterSpacing: "0.03em",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <span
              style={{
                width: 4,
                height: 4,
                borderRadius: "50%",
                background: allOnline ? "var(--ok)" : connectedCount > 0 ? "var(--warn)" : "var(--unknown)",
                display: "inline-block",
              }}
            />
            {connectedCount}/{registry.length}
          </span>
        </div>

        {/* Tab Switcher: ALL, DRONE, TURTLEBOT, CHARTS */}
        <div style={{ display: "flex", gap: 2, background: "var(--bg-3)", padding: 2, borderRadius: 5, border: "1px solid var(--border)" }}>
          <button
            onClick={() => setActiveTab("all")}
            style={{
              padding: "1px 7px",
              fontSize: 8.5,
              height: 19,
              borderRadius: 3,
              border: "none",
              background: activeTab === "all" ? "var(--bg-1)" : "transparent",
              color: activeTab === "all" ? "var(--accent)" : "var(--text-2)",
              fontWeight: activeTab === "all" ? 700 : 500,
              boxShadow: activeTab === "all" ? "0 1px 2px rgba(0,0,0,0.08)" : "none",
            }}
          >
            ALL
          </button>
          {registry.map((r) => {
            const isUav = r.robotType === "UAV";
            const shortName = isUav ? "DRONE" : "TURTLEBOT";
            return (
              <button
                key={r.robotId}
                onClick={() => setActiveTab(r.robotId)}
                style={{
                  padding: "1px 7px",
                  fontSize: 8.5,
                  height: 19,
                  borderRadius: 3,
                  border: "none",
                  background: activeTab === r.robotId ? "var(--bg-1)" : "transparent",
                  color: activeTab === r.robotId ? (isUav ? "var(--drone-color)" : "var(--bot-color)") : "var(--text-2)",
                  fontWeight: activeTab === r.robotId ? 700 : 500,
                  boxShadow: activeTab === r.robotId ? "0 1px 2px rgba(0,0,0,0.08)" : "none",
                }}
              >
                {isUav ? "🚁 " : "🤖 "} {shortName}
              </button>
            );
          })}
          <button
            onClick={() => setActiveTab("telemetry")}
            style={{
              padding: "1px 7px",
              fontSize: 8.5,
              height: 19,
              borderRadius: 3,
              border: "none",
              background: activeTab === "telemetry" ? "var(--bg-1)" : "transparent",
              color: activeTab === "telemetry" ? "var(--accent)" : "var(--text-2)",
              fontWeight: activeTab === "telemetry" ? 700 : 500,
              boxShadow: activeTab === "telemetry" ? "0 1px 2px rgba(0,0,0,0.08)" : "none",
            }}
          >
            CHARTS
          </button>
        </div>
      </div>

      {/* Scrollable Container with guaranteed scrolling */}
      <div
        className="robots-scroll-container"
        style={{
          flex: "1 1 0px",
          minHeight: 0,
          overflowY: "auto",
          overflowX: "hidden",
        }}
      >
        {registry.length === 0 && (
          <div className="empty-state" style={{ fontSize: 11, padding: "16px 0" }}>
            <div style={{ fontSize: 22, marginBottom: 6 }}>🤖</div>
            No robots registered
          </div>
        )}

        {activeTab !== "telemetry" &&
          displayedRobots.map((robot) => (
            <RobotCard
              key={robot.robotId}
              robot={{ ...robot, state: liveStates[robot.robotId] ?? robot.state }}
              isLeader={coordination.leader_id === robot.robotId}
              isFollower={coordination.follower_id === robot.robotId}
            />
          ))}

        {activeTab === "telemetry" && <TelemetryHistoryPanel />}
      </div>
    </div>
  );
}
