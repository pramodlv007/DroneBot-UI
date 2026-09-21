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
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from app.telemetry_store import PositionVelocitySample

# Prediction horizon in seconds
PREDICTION_HORIZON_S = 3.0
# Separation change threshold for trend classification (meters per 3s)
TREND_THRESHOLD_M = 0.3


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
        self._active_mode: CoordinationMode = CoordinationMode.IDLE
        self._role_switch_log: list[RoleSwitchRecord] = []
        self._max_linear_speed_mps = 0.22
        self._max_angular_speed_radps = 1.0
        self._stop_distance_m = 0.25

        # Attitude follow parameters (Roll, Pitch, Yaw)
        self._deadband_pitch_rad: float = 0.05
        self._deadband_roll_rad: float = 0.05
        self._deadband_yaw_rad: float = 0.05
        self._gain_pitch_linear: float = 0.8
        self._gain_yaw_angular: float = 1.5
        self._gain_roll_angular: float = 0.8

        # Separation history for trend detection
        self._separation_history: list[tuple[int, float]] = []  # (timestamp_ms, separation_m)
        self._max_separation_history = 30  # ~3s at 10Hz

    def configure_limits(self, max_linear_speed_mps: float, max_angular_speed_radps: float) -> None:
        self._max_linear_speed_mps = max_linear_speed_mps
        self._max_angular_speed_radps = max_angular_speed_radps

    def configure_attitude_follow(
        self,
        deadband_pitch_rad: float = 0.05,
        deadband_roll_rad: float = 0.05,
        deadband_yaw_rad: float = 0.05,
        gain_pitch_linear: float = 0.8,
        gain_yaw_angular: float = 1.5,
        gain_roll_angular: float = 0.8,
    ) -> None:
        self._deadband_pitch_rad = deadband_pitch_rad
        self._deadband_roll_rad = deadband_roll_rad
        self._deadband_yaw_rad = deadband_yaw_rad
        self._gain_pitch_linear = gain_pitch_linear
        self._gain_yaw_angular = gain_yaw_angular
        self._gain_roll_angular = gain_roll_angular

    @property
    def leader_id(self) -> str | None:
        return self._leader_id

    @property
    def follower_id(self) -> str | None:
        return self._follower_id

    @property
    def mode(self) -> CoordinationMode:
        return self._mode

    def set_mode(self, mode: CoordinationMode) -> None:
        self._mode = mode
        if mode != CoordinationMode.PAUSED:
            self._active_mode = mode

    @property
    def role_switch_log(self) -> list[RoleSwitchRecord]:
        return list(self._role_switch_log)

    def set_roles(
        self,
        leader_id: str | None,
        follower_id: str | None,
        robot_types: dict[str, RobotType],
        current_tracking_error_m: float | None = None,
        mode: CoordinationMode | None = None,
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
            self._active_mode = CoordinationMode.IDLE
            return

        if mode is not None:
            self._mode = mode
            self._active_mode = mode
            return

        leader_type = robot_types.get(leader_id)
        derived_mode = (
            CoordinationMode.TURTLE_FOLLOWS_DRONE
            if leader_type == RobotType.UAV
            else CoordinationMode.DRONE_FOLLOWS_TURTLE
        )
        self._mode = derived_mode
        self._active_mode = derived_mode

    def pause(self) -> None:
        self._mode = CoordinationMode.PAUSED

    def resume(self, robot_types: dict[str, RobotType]) -> None:
        """Un-pause by re-deriving mode or restoring active mode."""
        if self._leader_id is None or self._follower_id is None:
            self._mode = CoordinationMode.IDLE
            return
        if self._active_mode not in (CoordinationMode.IDLE, CoordinationMode.PAUSED):
            self._mode = self._active_mode
            return
        leader_type = robot_types.get(self._leader_id)
        self._mode = (
            CoordinationMode.TURTLE_FOLLOWS_DRONE
            if leader_type == RobotType.UAV
            else CoordinationMode.DRONE_FOLLOWS_TURTLE
        )
        self._active_mode = self._mode

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

        if self._mode == CoordinationMode.ATTITUDE_FOLLOW:
            return self._compute_attitude_follow(leader_state, follower_state)

        lx, ly = leader_state.pose.x, leader_state.pose.y
        fx, fy = follower_state.pose.x, follower_state.pose.y
        fyaw = follower_state.pose.yaw

        separation_m = horizontal_distance_m(lx, ly, fx, fy)
        tracking_error_m = abs(separation_m - self.target_separation_m)
        bearing = bearing_to_point_rad(fx, fy, lx, ly)
        heading_err_deg = heading_error_deg(bearing, fyaw)

        latency_ms = max(leader_state.telemetry_latency_ms, follower_state.telemetry_latency_ms)

        tracking_state = self._derive_tracking_state(tracking_error_m, leader_state, follower_state)

        # Compute relative velocity between leader and follower
        relative_vel = self._compute_relative_velocity(leader_state, follower_state)

        # Predictive separation (velocity extrapolation)
        predicted_sep, predicted_err = self.predict_separation(
            leader_state, follower_state
        )

        # Separation trend
        trend = self._compute_separation_trend(separation_m)

        coordination_state = CoordinationState(
            leader_id=self._leader_id,
            follower_id=self._follower_id,
            mode=self._mode,
            separation_m=separation_m,
            target_separation_m=self.target_separation_m,
            heading_error_deg=heading_err_deg,
            tracking_error_m=tracking_error_m,
            relative_velocity_mps=relative_vel,
            telemetry_latency_ms=latency_ms,
            predicted_separation_m=predicted_sep,
            predicted_tracking_error_m=predicted_err,
            separation_trend=trend,
            state=tracking_state,
        )

        command = None
        if self._mode != CoordinationMode.PAUSED and tracking_state != CoordinationTrackingState.LOST:
            command = self._go_to_point_command(follower_state, lx, ly, separation_m, bearing, fyaw)

        return coordination_state, command

    def _compute_relative_velocity(
        self, leader: RobotState, follower: RobotState
    ) -> float | None:
        """Compute scalar relative velocity magnitude between leader and follower."""
        if leader.velocity is None or follower.velocity is None:
            return None
        dvx = leader.velocity.linear_x - follower.velocity.linear_x
        dvy = leader.velocity.linear_y - follower.velocity.linear_y
        return round(math.hypot(dvx, dvy), 3)

    def predict_separation(
        self,
        leader_state: RobotState,
        follower_state: RobotState,
        horizon_s: float = PREDICTION_HORIZON_S,
    ) -> tuple[float | None, float | None]:
        """Extrapolate leader/follower positions forward by `horizon_s` using
        their current velocity vectors. Returns (predicted_separation_m,
        predicted_tracking_error_m) or (None, None) if velocity data is missing."""
        if leader_state.velocity is None or follower_state.velocity is None:
            return None, None

        # For UGV (differential drive): velocity is in body frame
        # Convert to mission frame using yaw
        def body_to_mission(vx: float, vy: float, yaw: float) -> tuple[float, float]:
            cos_y = math.cos(yaw)
            sin_y = math.sin(yaw)
            return vx * cos_y - vy * sin_y, vx * sin_y + vy * cos_y

        # Leader projected position
        if leader_state.robot_type == RobotType.UGV:
            lvx, lvy = body_to_mission(
                leader_state.velocity.linear_x,
                leader_state.velocity.linear_y,
                leader_state.pose.yaw,
            )
        else:
            # UAV velocities are typically already in mission frame (ENU)
            lvx = leader_state.velocity.linear_x
            lvy = leader_state.velocity.linear_y

        # Follower projected position
        if follower_state.robot_type == RobotType.UGV:
            fvx, fvy = body_to_mission(
                follower_state.velocity.linear_x,
                follower_state.velocity.linear_y,
                follower_state.pose.yaw,
            )
        else:
            fvx = follower_state.velocity.linear_x
            fvy = follower_state.velocity.linear_y

        pred_lx = leader_state.pose.x + lvx * horizon_s
        pred_ly = leader_state.pose.y + lvy * horizon_s
        pred_fx = follower_state.pose.x + fvx * horizon_s
        pred_fy = follower_state.pose.y + fvy * horizon_s

        predicted_sep = horizontal_distance_m(pred_lx, pred_ly, pred_fx, pred_fy)
        predicted_err = abs(predicted_sep - self.target_separation_m)

        return round(predicted_sep, 3), round(predicted_err, 3)

    def _compute_separation_trend(self, current_separation: float) -> str:
        """Classify separation trend as CONVERGING, STABLE, or DIVERGING
        based on recent separation history."""
        ts = now_ms()
        self._separation_history.append((ts, current_separation))
        # Keep only recent history
        if len(self._separation_history) > self._max_separation_history:
            self._separation_history = self._separation_history[-self._max_separation_history:]

        if len(self._separation_history) < 5:
            return "STABLE"

        # Compare current separation to the average of the oldest 5 samples
        old_avg = sum(s for _, s in self._separation_history[:5]) / 5
        new_avg = sum(s for _, s in self._separation_history[-5:]) / 5
        delta = new_avg - old_avg

        if delta > TREND_THRESHOLD_M:
            return "DIVERGING"
        elif delta < -TREND_THRESHOLD_M:
            return "CONVERGING"
        return "STABLE"

    def compute_mission_health_score(
        self,
        coordination_state: CoordinationState,
        robot_states: dict[str, RobotState],
        warning_count: int = 0,
        critical_count: int = 0,
    ) -> tuple[float, dict[str, float]]:
        """Compute a weighted 0–100 mission health score from live telemetry.

        Weights:
          - Tracking accuracy: 30%  (how close to target separation)
          - Communication/latency: 20%  (end-to-end telemetry lag)
          - Battery levels: 20%  (worst-case battery across fleet)
          - GPS quality: 15%  (fix type across fleet)
          - Safety events: 15%  (penalty for warnings/criticals)

        Returns (score, components_dict) where components_dict maps
        factor names to their individual 0–100 sub-scores.
        """
        components: dict[str, float] = {}

        # 1. Tracking accuracy (30%) — based on tracking error relative to lost threshold
        if coordination_state.tracking_error_m is not None:
            err_ratio = min(1.0, coordination_state.tracking_error_m / max(0.1, self.tracking_error_lost_m))
            components["tracking"] = round((1.0 - err_ratio) * 100, 1)
        else:
            components["tracking"] = 100.0 if coordination_state.state == CoordinationTrackingState.IDLE else 50.0

        # 2. Communication/latency (20%) — 0ms=100, 500ms+=0
        lat = coordination_state.telemetry_latency_ms
        if lat is not None and lat >= 0:
            lat_score = max(0.0, 100.0 - (lat / 5.0))  # 500ms → 0
            components["latency"] = round(lat_score, 1)
        else:
            components["latency"] = 50.0

        # 3. Battery (20%) — worst battery across all connected robots
        battery_scores = []
        for rs in robot_states.values():
            if rs.connected and rs.battery and rs.battery.percentage is not None:
                battery_scores.append(min(100.0, rs.battery.percentage))
        components["battery"] = round(min(battery_scores) if battery_scores else 50.0, 1)

        # 4. GPS quality (15%) — average fix quality (fix type 0–6 → 0–100)
        gps_scores = []
        for rs in robot_states.values():
            if rs.connected:
                if rs.gps and rs.gps.fix is not None:
                    gps_scores.append(min(100.0, (rs.gps.fix / 6.0) * 100))
                elif rs.robot_type == RobotType.UGV:
                    # UGVs use odometry, not GPS — treat as OK
                    gps_scores.append(80.0)
        components["gps"] = round(sum(gps_scores) / len(gps_scores) if gps_scores else 50.0, 1)

        # 5. Safety events (15%) — penalty per event
        event_penalty = min(100.0, warning_count * 5 + critical_count * 25)
        components["safety"] = round(max(0.0, 100.0 - event_penalty), 1)

        # Weighted composite
        score = (
            components["tracking"] * 0.30
            + components["latency"] * 0.20
            + components["battery"] * 0.20
            + components["gps"] * 0.15
            + components["safety"] * 0.15
        )
        return round(score, 1), components

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

    def _compute_attitude_follow(
        self, leader_state: RobotState, follower_state: RobotState
    ) -> tuple[CoordinationState, RobotCommand | None]:
        latency_ms = max(leader_state.telemetry_latency_ms, follower_state.telemetry_latency_ms)

        if not leader_state.connected or not follower_state.connected:
            tracking_state = CoordinationTrackingState.LOST
        elif latency_ms > 1000:
            tracking_state = CoordinationTrackingState.DEGRADED
        else:
            tracking_state = CoordinationTrackingState.TRACKING

        pitch = leader_state.pose.pitch
        roll = leader_state.pose.roll
        drone_yaw = leader_state.pose.yaw
        follower_yaw = follower_state.pose.yaw

        drone_pitch_deg = math.degrees(pitch)
        drone_roll_deg = math.degrees(roll)
        drone_yaw_deg = math.degrees(drone_yaw)

        yaw_error = normalize_angle_rad(drone_yaw - follower_yaw)
        heading_err_deg = math.degrees(yaw_error)

        separation_m = horizontal_distance_m(
            leader_state.pose.x, leader_state.pose.y, follower_state.pose.x, follower_state.pose.y
        )

        command, intent = self._attitude_follow_command(
            leader_state, follower_state, pitch, roll, yaw_error
        )

        coordination_state = CoordinationState(
            leader_id=self._leader_id,
            follower_id=self._follower_id,
            mode=self._mode,
            separation_m=separation_m,
            target_separation_m=None,
            heading_error_deg=round(heading_err_deg, 1),
            tracking_error_m=None,
            telemetry_latency_ms=latency_ms,
            drone_pitch_deg=round(drone_pitch_deg, 1),
            drone_roll_deg=round(drone_roll_deg, 1),
            drone_yaw_deg=round(drone_yaw_deg, 1),
            motion_intent=intent,
            state=tracking_state,
        )

        if tracking_state == CoordinationTrackingState.LOST or self._mode == CoordinationMode.PAUSED:
            command = None

        return coordination_state, command

    def _attitude_follow_command(
        self,
        leader_state: RobotState,
        follower_state: RobotState,
        pitch: float,
        roll: float,
        yaw_error: float,
    ) -> tuple[RobotCommand | None, str]:
        if follower_state.robot_type != RobotType.UGV:
            return None, "UNSUPPORTED_FOLLOWER"

        # Pitch -> forward/backward speed
        # In MAVLink, pitch < 0 is nose-down (forward acceleration), pitch > 0 is nose-up
        pitch_intent = -pitch
        if abs(pitch_intent) <= self._deadband_pitch_rad:
            v_raw = 0.0
        else:
            effective_pitch = pitch_intent - math.copysign(self._deadband_pitch_rad, pitch_intent)
            v_raw = effective_pitch * self._gain_pitch_linear

        # Alignment gating: scale forward speed by cos(yaw_error) so bot turns towards target
        alignment = max(0.0, math.cos(yaw_error))
        if v_raw >= 0:
            linear_x = v_raw * alignment
        else:
            linear_x = v_raw * alignment

        linear_x = max(-self._max_linear_speed_mps, min(self._max_linear_speed_mps, linear_x))

        # Yaw alignment: rotate to match drone's heading
        if abs(yaw_error) <= self._deadband_yaw_rad:
            w_yaw = 0.0
        else:
            effective_yaw = yaw_error - math.copysign(self._deadband_yaw_rad, yaw_error)
            w_yaw = effective_yaw * self._gain_yaw_angular

        # Roll steering: drone roll > 0 is tilt right -> turn right (w < 0)
        if abs(roll) <= self._deadband_roll_rad:
            w_roll = 0.0
        else:
            effective_roll = roll - math.copysign(self._deadband_roll_rad, roll)
            w_roll = -effective_roll * self._gain_roll_angular

        angular_z = w_yaw + w_roll
        angular_z = max(-self._max_angular_speed_radps, min(self._max_angular_speed_radps, angular_z))

        # Intent classification
        if abs(linear_x) < 0.02 and abs(angular_z) < 0.08:
            intent = "LEVEL / STATIONARY"
        elif linear_x >= 0.02 and abs(angular_z) < 0.15:
            intent = "DRIVING FORWARD"
        elif linear_x <= -0.02 and abs(angular_z) < 0.15:
            intent = "REVERSING"
        elif angular_z >= 0.15 and abs(linear_x) < 0.03:
            intent = "ROTATING LEFT"
        elif angular_z <= -0.15 and abs(linear_x) < 0.03:
            intent = "ROTATING RIGHT"
        elif linear_x > 0.02 and angular_z > 0.15:
            intent = "FORWARD + TURNING LEFT"
        elif linear_x > 0.02 and angular_z < -0.15:
            intent = "FORWARD + TURNING RIGHT"
        elif linear_x < -0.02 and angular_z > 0.15:
            intent = "REVERSE + TURNING LEFT"
        elif linear_x < -0.02 and angular_z < -0.15:
            intent = "REVERSE + TURNING RIGHT"
        else:
            intent = "FOLLOWING ATTITUDE"

        cmd = RobotCommand(
            robot_id=follower_state.robot_id,
            linear_x=round(linear_x, 3),
            angular_z=round(angular_z, 3),
            source="coordination_manager.attitude_follow",
        )
        return cmd, intent

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
