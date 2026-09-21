import { create } from "zustand";

// Mirrors AnomalyDetector.active_anomalies() — robot_id -> list of
// currently-ongoing anomaly types (only conditions with real sustained
// on/off state, e.g. "STUCK" / "HEADING_OSCILLATION"; point-in-time
// detections like a battery-drop or position-jump are events only, shown
// in the Timeline, not tracked here as ongoing state).
interface AnomalyStoreState {
  active: Record<string, string[]>;
  setAll: (active: Record<string, string[]>) => void;
}

export const useAnomalyStore = create<AnomalyStoreState>((set) => ({
  active: {},
  setAll: (active) => set({ active }),
}));
