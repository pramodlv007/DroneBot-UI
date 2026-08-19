"""
GatewayState — the single object holding every long-lived component
(registry, managers, recorder, supervisor, telemetry store, WS fan-out).
Built once in main.py's lifespan and reached via `request.app.state.gateway`
from routers, so routers stay thin and every component is constructed in
one place with explicit config wiring (no hidden globals/singletons).
"""

from __future__ import annotations

from app.config import Settings
from app.coordination_manager import CoordinationManager
from app.db import ExperimentRepository, SQLiteExperimentRepository
from app.experiment_recorder import ExperimentRecorder
from app.mission_manager import MissionManager
from app.robot_registry import RobotRegistry
from app.safety_manager import SafetyManager
from app.supervisor import build_supervisor
from app.supervisor.base import MissionSupervisor
from app.telemetry_store import TelemetryStore
from app.websocket import UIConnectionManager


class GatewayState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self.registry = RobotRegistry(settings.robots)
        self.mission_manager = MissionManager()
        self.coordination_manager = CoordinationManager(
            target_separation_m=settings.coordination.target_separation_m,
            tracking_error_degraded_m=settings.coordination.tracking_error_degraded_m,
            tracking_error_lost_m=settings.coordination.tracking_error_lost_m,
        )
        self.coordination_manager.configure_limits(
            settings.control.max_linear_speed_mps, settings.control.max_angular_speed_radps
        )
        self.safety_manager = SafetyManager(
            settings.safety, settings.control.max_linear_speed_mps, settings.control.max_angular_speed_radps
        )

        self.repository: ExperimentRepository = SQLiteExperimentRepository(settings.persistence.sqlite_path)
        self.experiment_recorder = ExperimentRecorder(self.repository)

        self.supervisor: MissionSupervisor = build_supervisor(settings)

        self.telemetry_store = TelemetryStore()
        self.ws_manager = UIConnectionManager()
