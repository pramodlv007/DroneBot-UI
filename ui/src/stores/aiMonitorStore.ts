import { create } from "zustand";
import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { useMissionStore } from "@/stores/missionStore";
import { useAnomalyStore } from "@/stores/anomalyStore";

// Shared polling core for /api/ai-monitor/update, used by both the full
// AI Monitor tab and the floating popup so opening both at once doesn't
// double the poll rate (or double-charge a real LLM call) — whichever
// view mounts first starts the shared interval, whichever unmounts last
// stops it.

export type RecommendedAction =
  | "CONTINUE"
  | "SLOW_DOWN"
  | "PAUSE"
  | "STOP"
  | "CHECK_GPS"
  | "CHECK_COMMUNICATION"
  | "RETURN_TO_SAFE_STATE";

export type MonitorProvider = "openai" | "claude" | "rule_based";

export interface MonitorPayload {
  headline: string;
  updates: string[];
  alerts: string[];
  overall_status: "NOMINAL" | "WARNING" | "CRITICAL";
  recommended_action: RecommendedAction;
  provider: MonitorProvider;
  timestamp_ms: number;
}

export interface FeedEntry extends MonitorPayload {
  id: number;
}

const POLL_INTERVAL_MS = 4000;
const MAX_FEED_ENTRIES = 20;

interface AiMonitorStoreState {
  feed: FeedEntry[];
  loading: boolean;
  error: string | null;
  consumers: number;
  timer: ReturnType<typeof setInterval> | null;
  idCounter: number;
  acquire: () => void;
  release: () => void;
  pollNow: () => Promise<void>;
  clearFeed: () => void;
}

export const useAiMonitorStore = create<AiMonitorStoreState>((set, get) => ({
  feed: [],
  loading: false,
  error: null,
  consumers: 0,
  timer: null,
  idCounter: 0,

  acquire: () => {
    const next = get().consumers + 1;
    set({ consumers: next });
    if (next === 1 && !get().timer) {
      get().pollNow();
      const timer = setInterval(() => get().pollNow(), POLL_INTERVAL_MS);
      set({ timer });
    }
  },

  release: () => {
    const next = Math.max(0, get().consumers - 1);
    set({ consumers: next });
    if (next === 0 && get().timer) {
      clearInterval(get().timer as ReturnType<typeof setInterval>);
      set({ timer: null });
    }
  },

  pollNow: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetch("/api/ai-monitor/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          robots: useRobotStore.getState().robots,
          coordination: useCoordinationStore.getState().coordination,
          mission: useMissionStore.getState().mission,
          system_health: useMissionStore.getState().systemHealth,
          anomalies: useAnomalyStore.getState().active,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload: MonitorPayload = await res.json();
      set((s) => ({
        feed: [{ ...payload, id: s.idCounter }, ...s.feed].slice(0, MAX_FEED_ENTRIES),
        idCounter: s.idCounter + 1,
      }));
    } catch (e: any) {
      set({ error: e?.message ?? "Failed to reach AI monitor endpoint" });
    } finally {
      set({ loading: false });
    }
  },

  clearFeed: () => set({ feed: [] }),
}));
