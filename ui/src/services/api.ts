import type { RegisteredRobot } from "@/types/robot";
import type { MissionState } from "@/types/mission";
import type { ExperimentDetail, ExperimentSummary } from "@/types/experiment";

const BASE = ""; // same-origin; vite dev server proxies /api -> backend

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}: ${body}`);
  }
  const contentType = res.headers.get("content-type") ?? "";
  return (contentType.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const api = {
  listRobots: () => request<RegisteredRobot[]>("/api/robots"),
  getRobot: (id: string) => request<RegisteredRobot>(`/api/robots/${id}`),
  connectRobot: (id: string) => request<RegisteredRobot>(`/api/robots/${id}/connect`, { method: "POST" }),
  disconnectRobot: (id: string) => request<RegisteredRobot>(`/api/robots/${id}/disconnect`, { method: "POST" }),
  updateRobotConfig: (id: string, body: Partial<{ connection: string; baud: number; target_system: number; target_component: number; namespace: string }>) =>
    request<RegisteredRobot>(`/api/robots/${id}/config`, { method: "PATCH", body: JSON.stringify(body) }),

  injectFault: (id: string, fault: Record<string, unknown>) =>
    request(`/api/robots/${id}/fault`, { method: "POST", body: JSON.stringify(fault) }),
  clearFault: (id: string) => request(`/api/robots/${id}/fault/clear`, { method: "POST" }),

  setDeadReckoning: (id: string, enabled: boolean) =>
    request<RegisteredRobot>(`/api/robots/${id}/dead-reckoning`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  resetDeadReckoning: (id: string) =>
    request<RegisteredRobot>(`/api/robots/${id}/dead-reckoning/reset`, { method: "POST" }),

  getMission: () => request<MissionState>("/api/mission"),
  startMission: (body: {
    leader_id: string;
    follower_id: string;
    mission_id?: string;
    recording?: boolean;
    experiment_name?: string;
  }) => request<MissionState>("/api/mission/start", { method: "POST", body: JSON.stringify(body) }),
  pauseMission: () => request<MissionState>("/api/mission/pause", { method: "POST" }),
  resumeMission: () => request<MissionState>("/api/mission/resume", { method: "POST" }),
  stopMission: () => request<MissionState>("/api/mission/stop", { method: "POST" }),
  emergencyStop: (source = "operator") =>
    request("/api/mission/emergency_stop", { method: "POST", body: JSON.stringify({ source }) }),
  clearEmergency: () => request<MissionState>("/api/mission/emergency_clear", { method: "POST" }),
  setRoles: (leader_id: string, follower_id: string) =>
    request("/api/mission/roles", { method: "POST", body: JSON.stringify({ leader_id, follower_id }) }),

  listExperiments: () => request<ExperimentSummary[]>("/api/experiments"),
  getExperiment: (id: string) => request<ExperimentDetail>(`/api/experiments/${id}`),
  getExperimentTelemetryAll: (id: string) =>
    request<{ robot_id: string; timestamp_ms: number; state_json: string }[]>(`/api/experiments/${id}/telemetry`),
  getExperimentCoordination: (id: string) => request<{ timestamp_ms: number; state_json: string }[]>(`/api/experiments/${id}/coordination`),
  getExperimentEvents: (id: string) => request<{ timestamp_ms: number; type: string; severity: string; message: string }[]>(`/api/experiments/${id}/events`),
  getExperimentRecommendations: (id: string) => request<{ timestamp_ms: number; recommendation_json: string }[]>(`/api/experiments/${id}/recommendations`),
  exportExperimentUrl: (id: string, format: "json" | "csv") => `/api/experiments/${id}/export?format=${format}`,

  getHealth: () => request<Record<string, unknown>>("/api/health"),
  setDeploymentMode: (mode: string) =>
    request<{ deploymentMode: string }>("/api/health/mode", {
      method: "PATCH",
      body: JSON.stringify({ mode }),
    }),
};
