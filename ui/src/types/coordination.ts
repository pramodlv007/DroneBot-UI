export type CoordinationMode =
  | "DRONE_FOLLOWS_TURTLE"
  | "TURTLE_FOLLOWS_DRONE"
  | "MANUAL"
  | "PAUSED"
  | "IDLE";

export type CoordinationTrackingState = "IDLE" | "TRACKING" | "DEGRADED" | "LOST" | "EMERGENCY";

export interface CoordinationState {
  leader_id: string | null;
  follower_id: string | null;
  mode: CoordinationMode;
  separation_m: number;
  target_separation_m: number | null;
  heading_error_deg: number | null;
  tracking_error_m: number | null;
  relative_velocity_mps: number | null;
  telemetry_latency_ms: number | null;
  state: CoordinationTrackingState;
  updated_at_ms: number;
}
