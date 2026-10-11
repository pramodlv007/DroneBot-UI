"""
Simulated UGV adapter. Unicycle kinematics driven by RobotCommand
(linear_x, angular_z). When no recent command has arrived (e.g. before a
mission starts) it runs an autonomous demo patrol — a gently wobbling loop
at TurtleBot3 Burger speed — so the dashboard shows live data for a demo.
"""

from __future__ import annotations

import asyncio
import math
import time

from app.coordinate_transformer import normalize_angle_rad
from app.fault_injection import fault_injection_registry
from app.models import (
    BatteryState,
    HealthState,
    Protocol,
    RobotCapability,
    RobotCommand,
    RobotPose,
    RobotRegistration,
    RobotState,
    RobotType,
    VelocityState,
    now_ms,
)

from .base import RobotAdapter

COMMAND_FRESH_WINDOW_S = 1.0

# Demo patrol: ~0.2 m/s around a ~2.5 m radius loop (Burger max is 0.22 m/s).
PATROL_SPEED_MPS = 0.2
PATROL_RADIUS_M = 2.5
PATROL_WOBBLE = 0.3          # fractional turn-rate variation -> non-circular path
PATROL_WOBBLE_RATE_RADPS = 0.05


class MockTurtleBotAdapter(RobotAdapter):
    def __init__(self, robot_id: str, display_name: str = "Simulated TurtleBot") -> None:
        self.robot_id = robot_id
        self.display_name = display_name
        self._connected = False
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._linear_v = 0.0
        self._angular_v = 0.0
        self._battery_pct = 100.0
        self._last_command_ms = 0
        self._task: asyncio.Task | None = None
        self._start_time = time.time()
        self._state = self._build_state()

    async def connect(self) -> RobotRegistration:
        self._connected = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._run())
        return RobotRegistration(
            robot_id=self.robot_id,
            robot_type=RobotType.UGV,
            protocol=Protocol.MOCK,
            display_name=self.display_name,
            capabilities=[
                RobotCapability.POSITION,
                RobotCapability.ODOMETRY,
                RobotCapability.BATTERY,
                RobotCapability.LINEAR_VELOCITY_CONTROL,
                RobotCapability.ANGULAR_VELOCITY_CONTROL,
            ],
            supported_commands=["velocity"],
        )

    async def disconnect(self) -> None:
        self._connected = False
        if self._task:
            self._task.cancel()
            self._task = None

    def get_state(self) -> RobotState:
        return self._state

    async def send_command(self, command: RobotCommand) -> None:
        self._linear_v = command.linear_x
        self._angular_v = command.angular_z
        self._last_command_ms = command.issued_at_ms

    async def _run(self) -> None:
        dt = 0.1
        try:
            while self._connected:
                self._tick(dt)
                self._state = self._build_state()
                self._emit(self._state)
                await asyncio.sleep(dt)
        except asyncio.CancelledError:
            pass

    def _tick(self, dt: float) -> None:
        fault = fault_injection_registry.get(self.robot_id)

        command_fresh = (now_ms() - self._last_command_ms) < COMMAND_FRESH_WINDOW_S * 1000
        if not command_fresh:
            t = time.time() - self._start_time
            self._linear_v = PATROL_SPEED_MPS
            self._angular_v = (PATROL_SPEED_MPS / PATROL_RADIUS_M) * (
                1.0 + PATROL_WOBBLE * math.sin(PATROL_WOBBLE_RATE_RADPS * t)
            )

        if not fault.odometry_freeze:
            self._x += self._linear_v * math.cos(self._yaw) * dt
            self._y += self._linear_v * math.sin(self._yaw) * dt
            self._yaw = normalize_angle_rad(self._yaw + self._angular_v * dt)

        self._battery_pct = max(
            0.0, self._battery_pct - 0.015 * dt * fault.battery_drain_rate_multiplier
        )

    def _build_state(self) -> RobotState:
        fault = fault_injection_registry.get(self.robot_id)
        source_ts = now_ms()

        connected = self._connected and not fault.forced_disconnect
        health = HealthState.NORMAL
        if not connected:
            health = HealthState.UNKNOWN
        elif self._battery_pct < 15:
            health = HealthState.WARNING

        t = time.time() - self._start_time
        # Small periodic jitter so the LAG readout looks like a real link.
        jitter_ms = int(15 + 10 * math.sin(1.3 * t))
        received_ts = source_ts + int(fault.extra_latency_ms) + jitter_ms

        # Floor-bump roll/pitch while moving — a few degrees at most.
        moving = bool(self._linear_v)
        roll = 0.02 * math.sin(2.1 * t) if moving else 0.0
        pitch = 0.015 * math.sin(1.7 * t + 0.5) if moving else 0.0

        command_fresh = (now_ms() - self._last_command_ms) < COMMAND_FRESH_WINDOW_S * 1000
        disturbance_x = fault.tracking_disturbance_m
        return RobotState(
            robot_id=self.robot_id,
            robot_type=RobotType.UGV,
            protocol=Protocol.MOCK,
            connected=connected,
            mode=(
                "TRACKING" if command_fresh
                else "PATROL" if self._linear_v or self._angular_v
                else "IDLE"
            ),
            health=health,
            pose=RobotPose(x=self._x + disturbance_x, y=self._y, z=0.0, roll=roll, pitch=pitch, yaw=self._yaw),
            velocity=VelocityState(linear_x=self._linear_v, angular_z=self._angular_v),
            battery=BatteryState(percentage=self._battery_pct, voltage=12.0 * (self._battery_pct / 100.0 * 0.2 + 0.8)),
            source_timestamp_ms=source_ts,
            received_timestamp_ms=received_ts,
        )
