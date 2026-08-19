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
from pydantic import BaseModel

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


class CoordinationConfig(BaseModel):
    target_separation_m: float = 1.5
    default_leader: Optional[str] = None
    default_follower: Optional[str] = None
    tracking_error_degraded_m: float = 2.0
    tracking_error_lost_m: float = 4.0


class ControlConfig(BaseModel):
    rate_hz: float = 10
    max_linear_speed_mps: float = 0.22
    max_angular_speed_radps: float = 1.0


class Settings(BaseModel):
    robots: dict[str, RobotConfig]
    safety: SafetyConfig
    gateway: GatewayConfig
    persistence: PersistenceConfig
    supervisor: SupervisorConfig
    coordination: CoordinationConfig
    control: ControlConfig
    deployment_mode: str = "SIMULATION"

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-5"


@lru_cache
def get_settings() -> Settings:
    robots_path = Path(os.environ.get("ROBOTS_CONFIG_PATH", REPO_ROOT / "config" / "robots.yaml"))
    mission_path = Path(os.environ.get("MISSION_CONFIG_PATH", REPO_ROOT / "config" / "mission.yaml"))
    system_path = Path(os.environ.get("SYSTEM_CONFIG_PATH", REPO_ROOT / "config" / "system.yaml"))

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
        deployment_mode=os.environ.get("DEPLOYMENT_MODE", system_raw.get("mode", "SIMULATION")),
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
    )
