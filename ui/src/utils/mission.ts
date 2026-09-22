import type { MissionState } from "@/types/mission";
import type { RobotState } from "@/types/robot";

export function isActiveMission(state: MissionState["state"]): boolean {
  return ["ARMED", "RUNNING", "PAUSED", "DEGRADED", "EMERGENCY"].includes(state);
}

export function startBlockReason(state: MissionState["state"], online: boolean,
  leaderId: string, followerId: string, robots: Record<string, Pick<RobotState, "connected">>): string | null {
  if (!online) return "Waiting for the gateway connection. Live controls will return when it reconnects.";
  if (isActiveMission(state)) return "Stop the current mission before starting another.";
  if (Object.values(robots).filter(r => r.connected).length < 2) return "Connect two robots to start a mission.";
  if (!leaderId || !followerId) return "Choose a leader and follower to continue.";
  if (leaderId === followerId) return "Choose a different robot for each role.";
  if (!robots[leaderId]?.connected || !robots[followerId]?.connected) return "Both selected robots must be connected.";
  return null;
}
