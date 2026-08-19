"""
Coordination Manager — computes CoordinationState (tracking error,
separation, heading error) from two robots' latest RobotState, derives the
follower's target velocity command (a go-to-point controller, the same
control law the legacy bridge used, now shared and unit-testable), and
owns leader/follower role switching + its audit trail.

This module never talks to an adapter directly — it returns a
RobotCommand for the caller (mission_manager) to pass through
SafetyManager.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.coordinate_transformer import (
    bearing_to_point_rad,
    heading_error_deg,
    horizontal_distance_m,
    normalize_angle_rad,
)
from app.models import (
    CoordinationMode,
    CoordinationState,
    CoordinationTrackingState,
    RobotCommand,
    RobotState,
    RobotType,
    now_ms,
)


@dataclass
class RoleSwitchRecord:
    timestamp_ms: int
    previous_leader: str | None
    previous_follower: str | None
    new_leader: str | None
    new_follower: str | None
    tracking_error_before_m: float | None
    tracking_error_after_m: float | None = None
    stabilization_time_s: float | None = None


class CoordinationManager:
    def __init__(
        self,
        target_separation_m: float,
        tracking_error_degraded_m: float,
        tracking_error_lost_m: float,
    ) -> None:
        self.target_separation_m = target_separation_m
        self.tracking_error_degraded_m = tracking_error_degraded_m
        self.tracking_error_lost_m = tracking_error_lost_m

        self._leader_id: str | None = None
        self._follower_id: str | None = None
        self._mode: CoordinationMode = CoordinationMode.IDLE
        self._role_switch_log: list[RoleSwitchRecord] = []
        self._max_linear_speed_mps = 0.22
        self._max_angular_speed_radps = 1.0
        self._stop_distance_m = 0.25

    def configure_limits(self, max_linear_speed_mps: float, max_angular_speed_radps: float) -> None:
        self._max_linear_speed_mps = max_linear_speed_mps
        self._max_angular_speed_radps = max_angular_speed_radps

    @property
    def leader_id(self) -> str | None:
        return self._leader_id

    @property
    def follower_id(self) -> str | None:
        return self._follower_id

    @property
    def mode(self) -> CoordinationMode:
        return self._mode

    @property
    def role_switch_log(self) -> list[RoleSwitchRecord]:
        return list(self._role_switch_log)

    def set_roles(
        self,
        leader_id: str | None,
        follower_id: str | None,
        robot_types: dict[str, RobotType],
        current_tracking_error_m: float | None = None,
    ) -> None:
        """Assign leader/follower and record a role-switch event if this
        changes an existing assignment (§13)."""
        if leader_id != self._leader_id or follower_id != self._follower_id:
            self._role_switch_log.append(
                RoleSwitchRecord(
                    timestamp_ms=now_ms(),
                    previous_leader=self._leader_id,
                    previous_follower=self._follower_id,
                    new_leader=leader_id,
                    new_follower=follower_id,
                    tracking_error_before_m=current_tracking_error_m,
                )
            )

        self._leader_id = leader_id
        self._follower_id = follower_id

        if leader_id is None or follower_id is None:
            self._mode = CoordinationMode.IDLE
            return

        leader_type = robot_types.get(leader_id)
        self._mode = (
            CoordinationMode.TURTLE_FOLLOWS_DRONE
            if leader_type == RobotType.UAV
            else CoordinationMode.DRONE_FOLLOWS_TURTLE
        )

    def pause(self) -> None:
        self._mode = CoordinationMode.PAUSED

    def resume(self, robot_types: dict[str, RobotType]) -> None:
        """Un-pause by re-deriving mode from the current leader/follower
        assignment (mirrors set_roles' mode derivation without touching
        the role-switch log)."""
        if self._leader_id is None or self._follower_id is None:
            self._mode = CoordinationMode.IDLE
            return
        leader_type = robot_types.get(self._leader_id)
        self._mode = (
            CoordinationMode.TURTLE_FOLLOWS_DRONE
            if leader_type == RobotType.UAV
            else CoordinationMode.DRONE_FOLLOWS_TURTLE
        )

    def compute(
        self, leader_state: RobotState | None, follower_state: RobotState | None
    ) -> tuple[CoordinationState, RobotCommand | None]:
        """Returns (CoordinationState for broadcast, RobotCommand for the
        follower or None if no command should be issued)."""

        if leader_state is None or follower_state is None or self._leader_id is None:
            return (
                CoordinationState(
                    leader_id=self._leader_id,
                    follower_id=self._follower_id,
                    mode=self._mode,
                    target_separation_m=self.target_separation_m,
                    state=CoordinationTrackingState.IDLE,
                ),
                None,
            )

        lx, ly = leader_state.pose.x, leader_state.pose.y
        fx, fy = follower_state.pose.x, follower_state.pose.y
        fyaw = follower_state.pose.yaw

        separation_m = horizontal_distance_m(lx, ly, fx, fy)
        tracking_error_m = abs(separation_m - self.target_separation_m)
        bearing = bearing_to_point_rad(fx, fy, lx, ly)
        heading_err_deg = heading_error_deg(bearing, fyaw)

        latency_ms = max(leader_state.telemetry_latency_ms, follower_state.telemetry_latency_ms)

        tracking_state = self._derive_tracking_state(tracking_error_m, leader_state, follower_state)

        coordination_state = CoordinationState(
            leader_id=self._leader_id,
            follower_id=self._follower_id,
            mode=self._mode,
            separation_m=separation_m,
            target_separation_m=self.target_separation_m,
            heading_error_deg=heading_err_deg,
            tracking_error_m=tracking_error_m,
            telemetry_latency_ms=latency_ms,
            state=tracking_state,
        )

        command = None
        if self._mode != CoordinationMode.PAUSED and tracking_state != CoordinationTrackingState.LOST:
            command = self._go_to_point_command(follower_state, lx, ly, separation_m, bearing, fyaw)

        return coordination_state, command

    def _derive_tracking_state(
        self, tracking_error_m: float, leader: RobotState, follower: RobotState
    ) -> CoordinationTrackingState:
        if not leader.connected or not follower.connected:
            return CoordinationTrackingState.LOST
        if tracking_error_m >= self.tracking_error_lost_m:
            return CoordinationTrackingState.LOST
        if tracking_error_m >= self.tracking_error_degraded_m:
            return CoordinationTrackingState.DEGRADED
        return CoordinationTrackingState.TRACKING

    def _go_to_point_command(
        self,
        follower_state: RobotState,
        target_x: float,
        target_y: float,
        distance_m: float,
        bearing_rad: float,
        follower_yaw: float,
    ) -> RobotCommand | None:
        """Same control law as the legacy drone_to_turtlebot_bridge.py
        go-to-point controller (§reusable components in docs/audit.md),
        generalized to work regardless of which robot is the follower."""

        if distance_m <= self._stop_distance_m:
            return RobotCommand(robot_id=follower_state.robot_id, linear_x=0.0, angular_z=0.0, source="coordination_manager")

        angle_error = normalize_angle_rad(bearing_rad - follower_yaw)

        if follower_state.robot_type == RobotType.UGV:
            angular = max(-self._max_angular_speed_radps, min(self._max_angular_speed_radps, 2.5 * angle_error))
            alignment = max(0.0, math.cos(angle_error))
            linear = self._max_linear_speed_mps * alignment
            return RobotCommand(robot_id=follower_state.robot_id, linear_x=linear, angular_z=angular, source="coordination_manager")

        # UAV follower: command ENU velocity directly toward the target,
        # capped at the configured max linear speed.
        dx = target_x - follower_state.pose.x
        dy = target_y - follower_state.pose.y
        dist = max(1e-6, math.hypot(dx, dy))
        speed = min(self._max_linear_speed_mps, dist)
        vx = (dx / dist) * speed
        vy = (dy / dist) * speed
        return RobotCommand(robot_id=follower_state.robot_id, linear_x=vx, linear_y=vy, source="coordination_manager")

    def record_stabilization(self, tracking_error_after_m: float) -> None:
        """Call periodically after a role switch; fills in the most recent
        switch record once tracking error re-stabilizes below the
        'degraded' threshold."""
        if not self._role_switch_log:
            return
        last = self._role_switch_log[-1]
        if last.tracking_error_after_m is None and tracking_error_after_m <= self.tracking_error_degraded_m:
            last.tracking_error_after_m = tracking_error_after_m
            last.stabilization_time_s = (now_ms() - last.timestamp_ms) / 1000.0
