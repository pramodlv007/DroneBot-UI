"""
Safety Manager — the single deterministic gate every outbound robot
command must pass through (§15). Nothing else in the backend calls
adapter.send_command() directly; mission_manager always routes through
SafetyManager.check_and_clamp() first.

Checks emergency and mission state, connection, robot identity, finite
velocity values, telemetry freshness, and command rate. Allowed commands
have horizontal speed and angular velocity clamped to configured limits.
Emergency zero commands deliberately bypass this gate (see docs/safety.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.config import SafetyConfig
from app.models import MissionStateEnum, RobotCommand, RobotState, now_ms


@dataclass
class SafetyCheckResult:
    allowed: bool
    reason: str | None = None
    command: RobotCommand | None = None


class SafetyManager:
    def __init__(self, config: SafetyConfig, max_linear_speed_mps: float, max_angular_speed_radps: float) -> None:
        self.config = config
        self.max_linear_speed_mps = max_linear_speed_mps
        self.max_angular_speed_radps = max_angular_speed_radps

        self._emergency = False
        self._emergency_reason: str | None = None
        self._emergency_at_ms: int | None = None
        self._emergency_source: str | None = None
        self._emergency_snapshot: dict[str, RobotState] = {}

        self._last_command_ms: dict[str, int] = {}
        self._min_command_interval_ms = 1000.0 / max(1.0, config.max_command_rate_hz)

    # -- emergency stop ------------------------------------------------

    @property
    def emergency(self) -> bool:
        return self._emergency

    def trigger_emergency_stop(self, source: str, robot_states: dict[str, RobotState]) -> None:
        self._emergency = True
        self._emergency_reason = f"Emergency stop triggered by {source}"
        self._emergency_at_ms = now_ms()
        self._emergency_source = source
        self._emergency_snapshot = dict(robot_states)

    def clear_emergency_stop(self) -> None:
        self._emergency = False
        self._emergency_reason = None
        self._emergency_at_ms = None
        self._emergency_source = None
        self._emergency_snapshot = {}

    def emergency_info(self) -> dict:
        return {
            "active": self._emergency,
            "reason": self._emergency_reason,
            "triggered_at_ms": self._emergency_at_ms,
            "source": self._emergency_source,
            "robot_states_at_trigger": {k: v.model_dump() for k, v in self._emergency_snapshot.items()},
        }

    # -- command gating --------------------------------------------------

    def check_and_clamp(
        self,
        command: RobotCommand,
        robot_state: RobotState | None,
        mission_state: MissionStateEnum,
    ) -> SafetyCheckResult:
        if self._emergency:
            return SafetyCheckResult(allowed=False, reason="EMERGENCY_STOP_ACTIVE")

        if mission_state not in (MissionStateEnum.RUNNING, MissionStateEnum.ARMED):
            return SafetyCheckResult(allowed=False, reason=f"MISSION_STATE_{mission_state.value}_DISALLOWS_COMMANDS")

        if robot_state is None or not robot_state.connected:
            return SafetyCheckResult(allowed=False, reason="ROBOT_NOT_CONNECTED")

        if command.robot_id != robot_state.robot_id:
            return SafetyCheckResult(allowed=False, reason="ROBOT_ID_MISMATCH")
        if not all(math.isfinite(value) for value in (command.linear_x, command.linear_y, command.angular_z)):
            return SafetyCheckResult(allowed=False, reason="NON_FINITE_COMMAND")

        now = now_ms()
        age_s = (now - robot_state.received_timestamp_ms) / 1000.0
        if age_s > self.config.telemetry_stale_s:
            return SafetyCheckResult(allowed=False, reason="TELEMETRY_STALE")

        last = self._last_command_ms.get(command.robot_id)
        if last is not None and (now - last) < self._min_command_interval_ms:
            return SafetyCheckResult(allowed=False, reason="COMMAND_RATE_LIMITED")

        speed = math.hypot(command.linear_x, command.linear_y)
        scale = min(1.0, self.max_linear_speed_mps / speed) if speed else 1.0
        clamped = command.model_copy(
            update={
                "linear_x": command.linear_x * scale,
                "linear_y": command.linear_y * scale,
                "angular_z": _clamp(command.angular_z, -self.max_angular_speed_radps, self.max_angular_speed_radps),
            }
        )
        self._last_command_ms[command.robot_id] = now
        return SafetyCheckResult(allowed=True, command=clamped)

    def is_telemetry_stale(self, robot_state: RobotState | None) -> bool:
        if robot_state is None:
            return True
        age_s = (now_ms() - robot_state.received_timestamp_ms) / 1000.0
        return age_s > self.config.telemetry_stale_s

    def is_heartbeat_lost(self, last_heartbeat_ms: int | None) -> bool:
        if last_heartbeat_ms is None:
            return True
        age_s = (now_ms() - last_heartbeat_ms) / 1000.0
        return age_s > self.config.heartbeat_timeout_s


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
