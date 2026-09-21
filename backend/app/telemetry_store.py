"""
In-memory live state: latest RobotState per robot, latest CoordinationState/
MissionState/SystemHealthState/SupervisorRecommendation, and a bounded
event-timeline ring buffer. This is what GET /api/* and new WebSocket
subscribers read on connect, before live updates start flowing; the
system-of-record for a *recorded* experiment is SQLite
(experiment_recorder.py), not this store.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

from app.models import (
    CoordinationState,
    MissionEvent,
    MissionState,
    RobotState,
    SupervisorRecommendation,
    SystemHealthState,
)

EVENT_BUFFER_SIZE = 500
VELOCITY_HISTORY_SIZE = 10  # ~1s at 10Hz control loop rate


@dataclass
class PositionVelocitySample:
    """Snapshot for velocity-based position extrapolation."""
    timestamp_ms: int
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float


class TelemetryStore:
    def __init__(self) -> None:
        self.robot_states: dict[str, RobotState] = {}
        self.coordination_state: CoordinationState = CoordinationState()
        self.mission_state: MissionState = MissionState()
        self.system_health: SystemHealthState = SystemHealthState()
        self.latest_recommendation: Optional[SupervisorRecommendation] = None
        self.events: deque[MissionEvent] = deque(maxlen=EVENT_BUFFER_SIZE)
        # Per-robot position+velocity history for prediction extrapolation
        self.velocity_history: dict[str, deque[PositionVelocitySample]] = {}

    def update_robot_state(self, state: RobotState) -> None:
        self.robot_states[state.robot_id] = state
        # Record position + velocity sample for prediction engine
        if state.robot_id not in self.velocity_history:
            self.velocity_history[state.robot_id] = deque(maxlen=VELOCITY_HISTORY_SIZE)
        sample = PositionVelocitySample(
            timestamp_ms=state.received_timestamp_ms,
            x=state.pose.x,
            y=state.pose.y,
            z=state.pose.z,
            vx=state.velocity.linear_x if state.velocity else 0.0,
            vy=state.velocity.linear_y if state.velocity else 0.0,
            vz=state.velocity.linear_z if state.velocity else 0.0,
        )
        self.velocity_history[state.robot_id].append(sample)

    def add_event(self, event: MissionEvent) -> None:
        self.events.append(event)

    def recent_events(self, limit: int = 100) -> list[MissionEvent]:
        return list(self.events)[-limit:]

    def get_velocity_history(self, robot_id: str) -> list[PositionVelocitySample]:
        """Return recent position/velocity samples for a robot."""
        return list(self.velocity_history.get(robot_id, []))
