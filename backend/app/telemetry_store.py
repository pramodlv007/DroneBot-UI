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


class TelemetryStore:
    def __init__(self) -> None:
        self.robot_states: dict[str, RobotState] = {}
        self.coordination_state: CoordinationState = CoordinationState()
        self.mission_state: MissionState = MissionState()
        self.system_health: SystemHealthState = SystemHealthState()
        self.latest_recommendation: Optional[SupervisorRecommendation] = None
        self.events: deque[MissionEvent] = deque(maxlen=EVENT_BUFFER_SIZE)

    def update_robot_state(self, state: RobotState) -> None:
        self.robot_states[state.robot_id] = state

    def add_event(self, event: MissionEvent) -> None:
        self.events.append(event)

    def recent_events(self, limit: int = 100) -> list[MissionEvent]:
        return list(self.events)[-limit:]
