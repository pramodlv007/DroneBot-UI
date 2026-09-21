"""
GatewayState — the single object holding every long-lived component
(registry, managers, recorder, supervisor, telemetry store, WS fan-out).
Built once in main.py's lifespan and reached via `request.app.state.gateway`
from routers, so routers stay thin and every component is constructed in
one place with explicit config wiring (no hidden globals/singletons).
"""

from __future__ import annotations

from app.anomaly_detector import AnomalyDetector
from app.config import Settings
from app.coordination_manager import CoordinationManager
from app.db import ExperimentRepository, SQLiteExperimentRepository
from app.experiment_recorder import ExperimentRecorder
from app.mission_manager import MissionManager
from app.models import MissionEvent
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
        att_cfg = settings.coordination.attitude_follow
        self.coordination_manager.configure_attitude_follow(
            deadband_pitch_rad=att_cfg.deadband_pitch_rad,
            deadband_roll_rad=att_cfg.deadband_roll_rad,
            deadband_yaw_rad=att_cfg.deadband_yaw_rad,
            gain_pitch_linear=att_cfg.gain_pitch_linear,
            gain_yaw_angular=att_cfg.gain_yaw_angular,
            gain_roll_angular=att_cfg.gain_roll_angular,
        )
        self.safety_manager = SafetyManager(
            settings.safety, settings.control.max_linear_speed_mps, settings.control.max_angular_speed_radps
        )

        self.repository: ExperimentRepository = SQLiteExperimentRepository(settings.persistence.sqlite_path)
        self.experiment_recorder = ExperimentRecorder(self.repository)

        self.supervisor: MissionSupervisor = build_supervisor(settings)

        self.telemetry_store = TelemetryStore()
        self.ws_manager = UIConnectionManager()
        self.anomaly_detector = AnomalyDetector(settings.anomaly)

    async def emit_event(self, event: MissionEvent) -> None:
        """The only path that should add a MissionEvent: stores it AND
        broadcasts it live over the 'events' WS topic. Routers/loops must
        `await gw.emit_event(...)` rather than calling
        telemetry_store.add_event() directly, or the Timeline panel will
        only ever see events that existed at initial-snapshot time."""
        self.telemetry_store.add_event(event)
        await self.ws_manager.broadcast("events", event.model_dump(mode="json"))

    async def clear_robot_telemetry(self, robot_id: str) -> None:
        """The only path that should drop a robot's live telemetry on
        disconnect: pops it from the store AND pushes one corrected
        connected=False snapshot to every already-open UI client first.

        Without the broadcast half of this, an already-open browser tab's
        cached copy of this robot (useRobotStore on the frontend, fed only
        by the 'robot_state' WS topic) never learns the robot went away —
        the backend just stops sending updates for that id, so the map and
        live-metrics bar keep rendering its last (connected=True) frame
        forever, even though a fresh REST poll (GET /api/robots, what the
        Robots panel's OFFLINE badge and CONNECT button use) already shows
        it offline. That mismatch — "OFFLINE" badge next to a still-live-
        looking map marker — is confusing enough to be worth this call on
        every disconnect path (REST disconnect, staleness watchdog, ingest
        socket close)."""
        state = self.telemetry_store.robot_states.pop(robot_id, None)
        if state is not None:
            offline_state = state.model_copy(update={"connected": False})
            await self.ws_manager.broadcast("robot_state", offline_state.model_dump(mode="json"))
