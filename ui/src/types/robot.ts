// Mirrors backend/app/models.py exactly (field names are snake_case to
// match the wire format the gateway actually sends — see
// docs/common_robot_model.md for why this mirror is kept manual rather
// than generated, and what breaks if the two drift apart).

export type RobotType = "UAV" | "UGV" | "MANIPULATOR" | "QUADRUPED" | "OTHER";

export type Protocol = "MAVLink" | "ROS2" | "Mock";

export type HealthState = "NORMAL" | "WARNING" | "CRITICAL" | "UNKNOWN";

export type RobotCapability =
  | "POSITION"
  | "GPS"
  | "ALTITUDE"
  | "ATTITUDE"
  | "ODOMETRY"
  | "BATTERY"
  | "LINEAR_VELOCITY_CONTROL"
  | "ANGULAR_VELOCITY_CONTROL"
  | "FLIGHT_MODE"
  | "ARM"
  | "DISARM";

export interface RobotPose {
  x: number;
  y: number;
  z: number;
  roll: number;
  pitch: number;
  yaw: number;
}

export interface GPSState {
  latitude: number;
  longitude: number;
  altitude: number;
  fix: number;
}

export interface VelocityState {
  linear_x: number;
  linear_y: number;
  linear_z: number;
  angular_x: number;
  angular_y: number;
  angular_z: number;
}

export interface BatteryState {
  voltage: number | null;
  current: number | null;
  percentage: number | null;
}

export interface RobotState {
  robot_id: string;
  robot_type: RobotType;
  protocol: Protocol;
  connected: boolean;
  mode: string | null;
  health: HealthState;
  pose: RobotPose;
  gps: GPSState | null;
  velocity: VelocityState | null;
  battery: BatteryState | null;
  capabilities: RobotCapability[];
  source_timestamp_ms: number;
  received_timestamp_ms: number;
  metadata: Record<string, unknown>;
}

// The shape GET /api/robots and /api/robots/{id} return (see
// backend/app/routers/robots_api.py's _serialize) — camelCase envelope
// around a snake_case RobotState, exactly what the backend emits.
export interface RobotConnectionParams {
  connection: string | null;
  baud: number | null;
  targetSystem: number | null;
  targetComponent: number | null;
  namespace: string | null;
  odomTopic: string | null;
  batteryTopic: string | null;
  cmdVelTopic: string | null;
}

// Indoor/GPS-denied dead-reckoning tracking (UAV only). `supported` is
// false for robot types/adapters that don't implement it (e.g. TurtleBots,
// which already get GPS-free position from wheel odometry) — the UI must
// hide the control entirely rather than show a button that always errors.
export interface DeadReckoningInfo {
  supported: boolean;
  enabled: boolean;
  active: boolean;
}

export interface RegisteredRobot {
  robotId: string;
  robotType: string;
  protocol: string;
  displayName: string;
  connected: boolean;
  // ROS2 robot armed via CONNECT, gateway waiting for its bridge node to
  // dial in and send telemetry.
  awaitingBridge: boolean;
  capabilities: string[];
  lastHeartbeatMs: number | null;
  state: RobotState | null;
  connection: RobotConnectionParams;
  deadReckoning: DeadReckoningInfo;
}
