import { create } from "zustand";
import type { MissionState, SystemHealthState, SupervisorRecommendation } from "@/types/mission";

const EMPTY_MISSION: MissionState = {
  mission_id: null,
  state: "DISCONNECTED",
  started_at_ms: null,
  updated_at_ms: 0,
  recording: false,
  experiment_id: null,
};

const EMPTY_HEALTH: SystemHealthState = {
  overall: "UNKNOWN",
  backend: "NORMAL",
  robots: {},
  supervisor: "UNKNOWN",
  updated_at_ms: 0,
};

interface MissionStoreState {
  mission: MissionState;
  emergencyActive: boolean;
  setEmergencyActive: (active: boolean) => void;
  systemHealth: SystemHealthState;
  supervisor: SupervisorRecommendation | null;
  setMission: (m: MissionState) => void;
  setSystemHealth: (h: SystemHealthState) => void;
  setSupervisor: (r: SupervisorRecommendation) => void;
}

export const useMissionStore = create<MissionStoreState>((set) => ({
  mission: EMPTY_MISSION,
  emergencyActive: false,
  setEmergencyActive: (emergencyActive) => set({ emergencyActive }),
  systemHealth: EMPTY_HEALTH,
  supervisor: null,
  setMission: (m) => set({ mission: m }),
  setSystemHealth: (h) => set({ systemHealth: h }),
  setSupervisor: (r) => set({ supervisor: r }),
}));
