"""
Mission Manager — the explicit mission state machine (§14) and the only
component that calls SafetyManager.check_and_clamp() + adapter.send_command().
UI requests always flow UI -> API -> MissionManager -> SafetyManager ->
RobotAdapter, never UI -> adapter directly (§15).
"""

from __future__ import annotations

from app.models import MissionState, MissionStateEnum, now_ms

_ALLOWED_TRANSITIONS: dict[MissionStateEnum, set[MissionStateEnum]] = {
    MissionStateEnum.DISCONNECTED: {MissionStateEnum.READY},
    MissionStateEnum.READY: {MissionStateEnum.ARMED, MissionStateEnum.DISCONNECTED},
    MissionStateEnum.ARMED: {MissionStateEnum.RUNNING, MissionStateEnum.READY, MissionStateEnum.EMERGENCY},
    MissionStateEnum.RUNNING: {
        MissionStateEnum.PAUSED,
        MissionStateEnum.DEGRADED,
        MissionStateEnum.EMERGENCY,
        MissionStateEnum.STOPPED,
        MissionStateEnum.COMPLETED,
    },
    MissionStateEnum.PAUSED: {MissionStateEnum.RUNNING, MissionStateEnum.STOPPED, MissionStateEnum.EMERGENCY},
    MissionStateEnum.DEGRADED: {
        MissionStateEnum.RUNNING,
        MissionStateEnum.EMERGENCY,
        MissionStateEnum.STOPPED,
    },
    MissionStateEnum.EMERGENCY: {MissionStateEnum.STOPPED, MissionStateEnum.READY},
    MissionStateEnum.STOPPED: {MissionStateEnum.READY},
    MissionStateEnum.COMPLETED: {MissionStateEnum.READY},
}


class InvalidTransitionError(Exception):
    pass


class MissionManager:
    def __init__(self) -> None:
        self._state = MissionState(state=MissionStateEnum.DISCONNECTED)

    @property
    def state(self) -> MissionState:
        return self._state

    def transition(self, new_state: MissionStateEnum, **updates) -> MissionState:
        current = self._state.state
        if new_state == current:
            return self._state
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if new_state not in allowed:
            raise InvalidTransitionError(f"{current.value} -> {new_state.value} is not a permitted transition")

        self._state = self._state.model_copy(update={"state": new_state, "updated_at_ms": now_ms(), **updates})
        return self._state

    def start(self, mission_id: str, experiment_id: str | None, recording: bool) -> MissionState:
        self.transition(
            MissionStateEnum.RUNNING,
            mission_id=mission_id,
            started_at_ms=now_ms(),
            experiment_id=experiment_id,
            recording=recording,
        )
        return self._state

    def pause(self) -> MissionState:
        return self.transition(MissionStateEnum.PAUSED)

    def resume(self) -> MissionState:
        return self.transition(MissionStateEnum.RUNNING)

    def stop(self) -> MissionState:
        return self.transition(MissionStateEnum.STOPPED)

    def degrade(self) -> MissionState:
        if self._state.state == MissionStateEnum.RUNNING:
            return self.transition(MissionStateEnum.DEGRADED)
        return self._state

    def recover(self) -> MissionState:
        if self._state.state == MissionStateEnum.DEGRADED:
            return self.transition(MissionStateEnum.RUNNING)
        return self._state

    def emergency(self) -> MissionState:
        return self.transition(MissionStateEnum.EMERGENCY)

    def ready(self) -> MissionState:
        return self.transition(MissionStateEnum.READY)
