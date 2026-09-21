"""
Common Robot Model — the single protocol-agnostic schema every adapter
normalizes into and every consumer (WebSocket clients, the UI, the
experiment recorder, the LLM supervisor) reads from.

Nothing outside backend/app/adapters/ should ever import pymavlink or
rclpy/ROS2 message types. If you find yourself reaching for MAVLink or
nav_msgs types anywhere else in this package, that's a layering violation.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def now_ms() -> int:
    return int(time.time() * 1000)


class RobotType(str, Enum):
    UAV = "UAV"
    UGV = "UGV"
    MANIPULATOR = "MANIPULATOR"
    QUADRUPED = "QUADRUPED"
    OTHER = "OTHER"


class Protocol(str, Enum):
    MAVLINK = "MAVLink"
    ROS2 = "ROS2"
    MOCK = "Mock"


class HealthState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class RobotCapability(str, Enum):
    POSITION = "POSITION"
    GPS = "GPS"
    ALTITUDE = "ALTITUDE"
    ATTITUDE = "ATTITUDE"
    ODOMETRY = "ODOMETRY"
    BATTERY = "BATTERY"
    LINEAR_VELOCITY_CONTROL = "LINEAR_VELOCITY_CONTROL"
    ANGULAR_VELOCITY_CONTROL = "ANGULAR_VELOCITY_CONTROL"
    FLIGHT_MODE = "FLIGHT_MODE"
    ARM = "ARM"
    DISARM = "DISARM"


class RobotPose(BaseModel):
    """Position + orientation in the shared `mission_map` frame (ENU meters,
    radians). See docs/coordinate_frames.md for the full frame contract."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


class GPSState(BaseModel):
    latitude: float
    longitude: float
    altitude: float
    fix: int = 0


class VelocityState(BaseModel):
    linear_x: float = 0.0
    linear_y: float = 0.0
    linear_z: float = 0.0
    angular_x: float = 0.0
    angular_y: float = 0.0
    angular_z: float = 0.0


class BatteryState(BaseModel):
    voltage: Optional[float] = None
    current: Optional[float] = None
    percentage: Optional[float] = None


class RobotState(BaseModel):
    robot_id: str
    robot_type: RobotType
    protocol: Protocol

    connected: bool
    mode: Optional[str] = None
    health: HealthState = HealthState.UNKNOWN

    pose: RobotPose
    gps: Optional[GPSState] = None
    velocity: Optional[VelocityState] = None
    battery: Optional[BatteryState] = None

    capabilities: list[RobotCapability] = Field(default_factory=list)

    # Timestamps, per spec §56: both the source's own clock and the
    # gateway's receive clock, so end-to-end latency is a real measurement,
    # not an estimate.
    source_timestamp_ms: int = Field(default_factory=now_ms)
    received_timestamp_ms: int = Field(default_factory=now_ms)

    @property
    def telemetry_latency_ms(self) -> float:
        return max(0.0, self.received_timestamp_ms - self.source_timestamp_ms)

    metadata: dict[str, Any] = Field(default_factory=dict)


class RobotRegistration(BaseModel):
    """What an adapter declares about itself to the registry at connect time."""

    robot_id: str
    robot_type: RobotType
    protocol: Protocol
    display_name: str
    capabilities: list[RobotCapability]
    supported_commands: list[str] = Field(default_factory=list)


class CoordinationMode(str, Enum):
    DRONE_FOLLOWS_TURTLE = "DRONE_FOLLOWS_TURTLE"
    TURTLE_FOLLOWS_DRONE = "TURTLE_FOLLOWS_DRONE"
    ATTITUDE_FOLLOW = "ATTITUDE_FOLLOW"
    MANUAL = "MANUAL"
    PAUSED = "PAUSED"
    IDLE = "IDLE"


class CoordinationTrackingState(str, Enum):
    IDLE = "IDLE"
    TRACKING = "TRACKING"
    DEGRADED = "DEGRADED"
    LOST = "LOST"
    EMERGENCY = "EMERGENCY"


class CoordinationState(BaseModel):
    leader_id: Optional[str] = None
    follower_id: Optional[str] = None
    mode: CoordinationMode = CoordinationMode.IDLE

    separation_m: float = 0.0
    target_separation_m: Optional[float] = None
    heading_error_deg: Optional[float] = None
    tracking_error_m: Optional[float] = None
    relative_velocity_mps: Optional[float] = None
    telemetry_latency_ms: Optional[float] = None

    # Predictive separation alerting — velocity-extrapolated positions ~3s ahead
    predicted_separation_m: Optional[float] = None
    predicted_tracking_error_m: Optional[float] = None
    separation_trend: Optional[str] = None  # "CONVERGING" | "STABLE" | "DIVERGING"

    # Mission health score — weighted composite 0–100
    mission_health_score: Optional[float] = None
    mission_health_components: dict[str, Any] = Field(default_factory=dict)

    # Attitude follower telemetry
    drone_pitch_deg: Optional[float] = None
    drone_roll_deg: Optional[float] = None
    drone_yaw_deg: Optional[float] = None
    motion_intent: Optional[str] = None

    state: CoordinationTrackingState = CoordinationTrackingState.IDLE
    updated_at_ms: int = Field(default_factory=now_ms)


class MissionStateEnum(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    READY = "READY"
    ARMED = "ARMED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    EMERGENCY = "EMERGENCY"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"


class MissionState(BaseModel):
    mission_id: Optional[str] = None
    state: MissionStateEnum = MissionStateEnum.DISCONNECTED
    started_at_ms: Optional[int] = None
    updated_at_ms: int = Field(default_factory=now_ms)
    recording: bool = False
    experiment_id: Optional[str] = None


class SystemHealthState(BaseModel):
    overall: HealthState = HealthState.UNKNOWN
    backend: HealthState = HealthState.NORMAL
    robots: dict[str, HealthState] = Field(default_factory=dict)
    supervisor: HealthState = HealthState.UNKNOWN
    updated_at_ms: int = Field(default_factory=now_ms)


class EventSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class MissionEvent(BaseModel):
    timestamp_ms: int = Field(default_factory=now_ms)
    type: str
    severity: EventSeverity = EventSeverity.INFO
    robot_ids: list[str] = Field(default_factory=list)
    message: str = ""
    value: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecommendedAction(str, Enum):
    CONTINUE = "CONTINUE"
    SLOW_DOWN = "SLOW_DOWN"
    PAUSE = "PAUSE"
    STOP = "STOP"
    CHECK_GPS = "CHECK_GPS"
    CHECK_COMMUNICATION = "CHECK_COMMUNICATION"
    RETURN_TO_SAFE_STATE = "RETURN_TO_SAFE_STATE"


class SupervisorRecommendation(BaseModel):
    status: HealthState
    summary: str
    detected_issue: Optional[str] = None
    recommended_action: RecommendedAction
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str = ""
    timestamp_ms: int = Field(default_factory=now_ms)
    latency_ms: Optional[float] = None
    provider: str = "disabled"


class RobotCommand(BaseModel):
    """The only shape a velocity command may take anywhere past the
    SafetyManager. Never constructed directly from a raw UI payload —
    always passed through SafetyManager.clamp().

    UGVs (unicycle/differential-drive) use linear_x (body-frame forward
    speed, m/s) + angular_z (yaw rate, rad/s) and ignore linear_y.
    UAVs in follower mode use linear_x/linear_y as mission_map ENU
    velocity components (m/s) and treat angular_z as an optional yaw rate.
    """

    robot_id: str
    linear_x: float = 0.0
    linear_y: float = 0.0
    angular_z: float = 0.0
    issued_at_ms: int = Field(default_factory=now_ms)
    source: str = "mission_manager"
