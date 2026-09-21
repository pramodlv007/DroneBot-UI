// Single WebSocket connection to the gateway's /ws endpoint. This is the
// ONLY place in the frontend that parses the {"topic", "data"} envelope —
// every component reads from the Zustand stores below, never from the
// socket directly, which is what keeps components protocol-agnostic
// (§4: the browser never branches on "is this MAVLink or ROS2").

import { useRobotStore } from "@/stores/robotStore";
import { useCoordinationStore } from "@/stores/coordinationStore";
import { useMissionStore } from "@/stores/missionStore";
import { useEventStore } from "@/stores/eventStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useAnomalyStore } from "@/stores/anomalyStore";
import type { RobotState } from "@/types/robot";
import type { CoordinationState } from "@/types/coordination";
import type { MissionEvent, MissionState, SupervisorRecommendation, SystemHealthState } from "@/types/mission";

interface Envelope {
  topic: string;
  data: unknown;
}

interface Snapshot {
  robots: Record<string, RobotState>;
  coordination: CoordinationState;
  mission: MissionState;
  systemHealth: SystemHealthState;
  events: MissionEvent[];
  supervisor: SupervisorRecommendation | null;
  anomalies: Record<string, string[]>;
}

const RECONNECT_DELAY_MS = 2000;

export function connectGatewaySocket(): () => void {
  let ws: WebSocket | null = null;
  let closedByCaller = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

  function connect() {
    useConnectionStore.getState().setWsStatus("CONNECTING");
    ws = new WebSocket(url);

    ws.onopen = () => useConnectionStore.getState().setWsStatus("OPEN");

    ws.onmessage = (event) => {
      const envelope = JSON.parse(event.data) as Envelope;
      dispatch(envelope);
    };

    ws.onerror = () => useConnectionStore.getState().setWsStatus("ERROR");

    ws.onclose = () => {
      useConnectionStore.getState().setWsStatus("CLOSED");
      if (!closedByCaller) {
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };
  }

  function dispatch(envelope: Envelope) {
    switch (envelope.topic) {
      case "snapshot": {
        const snap = envelope.data as Snapshot;
        useRobotStore.getState().setAll(snap.robots);
        useCoordinationStore.getState().set(snap.coordination);
        useMissionStore.getState().setMission(snap.mission);
        useMissionStore.getState().setSystemHealth(snap.systemHealth);
        useEventStore.getState().setAll(snap.events);
        if (snap.supervisor) useMissionStore.getState().setSupervisor(snap.supervisor);
        useAnomalyStore.getState().setAll(snap.anomalies ?? {});
        break;
      }
      case "robot_state":
        useRobotStore.getState().upsert(envelope.data as RobotState);
        break;
      case "coordination_state":
        useCoordinationStore.getState().set(envelope.data as CoordinationState);
        break;
      case "mission_state":
        useMissionStore.getState().setMission(envelope.data as MissionState);
        break;
      case "system_health":
        useMissionStore.getState().setSystemHealth(envelope.data as SystemHealthState);
        break;
      case "supervisor_state":
        useMissionStore.getState().setSupervisor(envelope.data as SupervisorRecommendation);
        break;
      case "events":
        useEventStore.getState().add(envelope.data as MissionEvent);
        break;
      case "anomalies":
        useAnomalyStore.getState().setAll(envelope.data as Record<string, string[]>);
        break;
      default:
        break;
    }
  }

  connect();

  return () => {
    closedByCaller = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    ws?.close();
  };
}
