import { create } from "zustand";
import type { MissionEvent } from "@/types/mission";

const MAX_EVENTS = 500;

interface EventStoreState {
  events: MissionEvent[];
  add: (event: MissionEvent) => void;
  setAll: (events: MissionEvent[]) => void;
}

export const useEventStore = create<EventStoreState>((set) => ({
  events: [],
  add: (event) => set((s) => ({ events: [...s.events, event].slice(-MAX_EVENTS) })),
  setAll: (events) => set({ events }),
}));
