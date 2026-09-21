"""
Loads config/robots.yaml, config/mission.yaml, config/system.yaml plus
environment variables (.env) into typed settings objects. This is the only
module allowed to read YAML files or os.environ directly — everything else
receives config through these objects.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class RobotConfig(BaseModel):
    type: str
    protocol: str
    display_name: str
    capabilities: list[str] = []

    # MAVLink-specific
    connection: Optional[str] = None
    baud: Optional[int] = None
    target_system: Optional[int] = None
    target_component: Optional[int] = None

    # ROS2-specific
    namespace: Optional[str] = None
    odom_topic: Optional[str] = None
    battery_topic: Optional[str] = None
    cmd_vel_topic: Optional[str] = None


class SafetyConfig(BaseModel):
    max_tracking_error_m: float = 3.0
    max_latency_ms: float = 500
    heartbeat_timeout_s: float = 2.0
    telemetry_stale_s: float = 2.0
    max_command_rate_hz: float = 20
    min_battery_percent: float = 15


class GatewayConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    ws_ingest_path: str = "/ws/ingest"
    cors_origins: list[str] = ["http://localhost:5173"]


class PersistenceConfig(BaseModel):
    driver: str = "sqlite"
    sqlite_path: str = "./data/experiments.db"


class SupervisorConfig(BaseModel):
    provider: str = "mock"
    interval_s: float = 5.0


class AttitudeFollowConfig(BaseModel):
    deadband_pitch_rad: float = 0.05  # ~2.8 deg
    deadband_roll_rad: float = 0.05
    deadband_yaw_rad: float = 0.05
    gain_pitch_linear: float = 0.8    # (m/s) per rad of pitch
    gain_yaw_angular: float = 1.5     # (rad/s) per rad of yaw error
    gain_roll_angular: float = 0.8    # (rad/s) per rad of roll banking


class CoordinationConfig(BaseModel):
    target_separation_m: float = 1.5
    default_leader: Optional[str] = None
    default_follower: Optional[str] = None
    tracking_error_degraded_m: float = 2.0
    tracking_error_lost_m: float = 4.0
    attitude_follow: AttitudeFollowConfig = Field(default_factory=AttitudeFollowConfig)


class ControlConfig(BaseModel):
    rate_hz: float = 10
    max_linear_speed_mps: float = 0.22
    max_angular_speed_radps: float = 1.0


class AnomalyConfig(BaseModel):
    """Thresholds for AnomalyDetector's always-on sliding-window checks
    (backend/app/anomaly_detector.py) — runs every control-loop tick
    regardless of whether any UI panel is open, unlike the AI Monitor's
    rule engine which only evaluates while that tab is being polled."""

    enabled: bool = True

    # STUCK: robot has been continuously, non-trivially commanded for this
    # long but has displaced less than stuck_distance_m.
    stuck_window_s: float = 4.0
    stuck_command_threshold: float = 0.03  # m/s or rad/s to count as "actively commanded"
    stuck_distance_m: float = 0.05

    # BATTERY_DRAIN: percentage drop within the window that's faster than
    # any normal mission profile.
    battery_window_s: float = 30.0
    battery_drop_pct: float = 5.0

    # POSITION_JUMP: implied speed between two consecutive telemetry samples
    # that exceeds physical plausibility (sensor glitch / EKF reset / bad
    # dead-reckoning integration), not a genuine maneuver.
    position_jump_max_speed_mps: float = 8.0

    # HEADING_OSCILLATION: yaw-rate direction reversals within the window
    # that indicate an unstable controller or noisy heading estimate.
    heading_oscillation_window_s: float = 2.0
    heading_oscillation_min_flips: int = 4
    heading_oscillation_min_rate_radps: float = 0.3

    # Minimum time before the same anomaly type can re-fire for the same robot.
    cooldown_s: float = 20.0


class Settings(BaseModel):
    robots: dict[str, RobotConfig]
    safety: SafetyConfig
    gateway: GatewayConfig
    persistence: PersistenceConfig
    supervisor: SupervisorConfig
    coordination: CoordinationConfig
    control: ControlConfig
    anomaly: AnomalyConfig
    deployment_mode: str = "SIMULATION"

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-5"


def _resolve_config_path(env_var: str, default_relative: str) -> Path:
    """Resolve a config-file path from an env var override or the built-in
    default. A relative override (e.g. ROBOTS_CONFIG_PATH=./config/robots.yaml,
    as shipped in .env.example) must resolve against REPO_ROOT, not the
    process's working directory — the gateway is normally launched with its
    CWD at backend/ (dev script, Dockerfile), so a CWD-relative path would
    silently miss the file and load an empty config instead of erroring."""
    raw = os.environ.get(env_var)
    if not raw:
        return REPO_ROOT / default_relative
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


@lru_cache
def get_settings() -> Settings:
    robots_path = _resolve_config_path("ROBOTS_CONFIG_PATH", "config/robots.yaml")
    mission_path = _resolve_config_path("MISSION_CONFIG_PATH", "config/mission.yaml")
    system_path = _resolve_config_path("SYSTEM_CONFIG_PATH", "config/system.yaml")

    robots_raw = _load_yaml(robots_path).get("robots", {})
    mission_raw = _load_yaml(mission_path)
    system_raw = _load_yaml(system_path)

    return Settings(
        robots={rid: RobotConfig(**cfg) for rid, cfg in robots_raw.items()},
        safety=SafetyConfig(**system_raw.get("safety", {})),
        gateway=GatewayConfig(**system_raw.get("gateway", {})),
        persistence=PersistenceConfig(**system_raw.get("persistence", {})),
        supervisor=SupervisorConfig(**system_raw.get("supervisor", {})),
        coordination=CoordinationConfig(**mission_raw.get("coordination", {})),
        control=ControlConfig(**mission_raw.get("control", {})),
        anomaly=AnomalyConfig(**system_raw.get("anomaly", {})),
        deployment_mode=os.environ.get("DEPLOYMENT_MODE", system_raw.get("mode", "SIMULATION")),
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
    )
