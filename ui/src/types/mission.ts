export type MissionStateEnum =
  | "DISCONNECTED"
  | "READY"
  | "ARMED"
  | "RUNNING"
  | "PAUSED"
  | "DEGRADED"
  | "EMERGENCY"
  | "STOPPED"
  | "COMPLETED";

export interface MissionState {
  mission_id: string | null;
  state: MissionStateEnum;
  started_at_ms: number | null;
  updated_at_ms: number;
  recording: boolean;
  experiment_id: string | null;
}

export interface SystemHealthState {
  overall: string;
  backend: string;
  robots: Record<string, string>;
  supervisor: string;
  updated_at_ms: number;
}

export type EventSeverity = "INFO" | "WARNING" | "CRITICAL";

export interface MissionEvent {
  timestamp_ms: number;
  type: string;
  severity: EventSeverity;
  robot_ids: string[];
  message: string;
  value: number | null;
  metadata: Record<string, unknown>;
}

export type RecommendedAction =
  | "CONTINUE"
  | "SLOW_DOWN"
  | "PAUSE"
  | "STOP"
  | "CHECK_GPS"
  | "CHECK_COMMUNICATION"
  | "RETURN_TO_SAFE_STATE";

export interface SupervisorRecommendation {
  status: string;
  summary: string;
  detected_issue: string | null;
  recommended_action: RecommendedAction;
  confidence: number;
  reasoning_summary: string;
  timestamp_ms: number;
  latency_ms: number | null;
  provider: string;
}
