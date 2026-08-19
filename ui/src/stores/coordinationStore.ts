import { create } from "zustand";
import type { CoordinationState } from "@/types/coordination";

const EMPTY: CoordinationState = {
  leader_id: null,
  follower_id: null,
  mode: "IDLE",
  separation_m: 0,
  target_separation_m: null,
  heading_error_deg: null,
  tracking_error_m: null,
  relative_velocity_mps: null,
  telemetry_latency_ms: null,
  state: "IDLE",
  updated_at_ms: 0,
};

interface CoordinationStoreState {
  coordination: CoordinationState;
  history: { t: number; trackingError: number | null; separation: number | null; latency: number | null }[];
  set: (state: CoordinationState) => void;
}

const MAX_HISTORY = 300; // ~30s at 10Hz — enough for the live sparkline, full history lives in the experiment DB

export const useCoordinationStore = create<CoordinationStoreState>((set) => ({
  coordination: EMPTY,
  history: [],
  set: (state) =>
    set((s) => ({
      coordination: state,
      history: [
        ...s.history,
        {
          t: state.updated_at_ms,
          trackingError: state.tracking_error_m,
          separation: state.separation_m,
          latency: state.telemetry_latency_ms,
        },
      ].slice(-MAX_HISTORY),
    })),
}));
