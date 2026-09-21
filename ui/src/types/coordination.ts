export type CoordinationMode =
  | "DRONE_FOLLOWS_TURTLE"
  | "TURTLE_FOLLOWS_DRONE"
  | "ATTITUDE_FOLLOW"
  | "MANUAL"
  | "PAUSED"
  | "IDLE";

export type CoordinationTrackingState = "IDLE" | "TRACKING" | "DEGRADED" | "LOST" | "EMERGENCY";

export type SeparationTrend = "CONVERGING" | "STABLE" | "DIVERGING";

export interface MissionHealthComponents {
  tracking: number;
  latency: number;
  battery: number;
  gps: number;
  safety: number;
}

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

  // Predictive separation alerting (backend-computed)
  predicted_separation_m: number | null;
  predicted_tracking_error_m: number | null;
  separation_trend: SeparationTrend | null;

  // Mission health score (backend-computed, 0–100)
  mission_health_score: number | null;
  mission_health_components: MissionHealthComponents | null;

  drone_pitch_deg?: number | null;
  drone_roll_deg?: number | null;
  drone_yaw_deg?: number | null;
  motion_intent?: string | null;
  state: CoordinationTrackingState;
  updated_at_ms: number;
}
