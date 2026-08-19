import { create } from "zustand";

export type SocketStatus = "CONNECTING" | "OPEN" | "CLOSED" | "ERROR";

interface ConnectionStoreState {
  wsStatus: SocketStatus;
  setWsStatus: (status: SocketStatus) => void;
}

export const useConnectionStore = create<ConnectionStoreState>((set) => ({
  wsStatus: "CONNECTING",
  setWsStatus: (status) => set({ wsStatus: status }),
}));
