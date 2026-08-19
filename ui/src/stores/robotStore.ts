import { create } from "zustand";
import type { RobotState } from "@/types/robot";

interface RobotStoreState {
  robots: Record<string, RobotState>;
  upsert: (state: RobotState) => void;
  setAll: (states: Record<string, RobotState>) => void;
}

export const useRobotStore = create<RobotStoreState>((set) => ({
  robots: {},
  upsert: (state) =>
    set((s) => ({ robots: { ...s.robots, [state.robot_id]: state } })),
  setAll: (states) => set({ robots: states }),
}));
