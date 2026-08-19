"""
Simulated UAV adapter. Flies a scripted circular holding pattern by default
(leader behavior); when it recently received a RobotCommand (follower
behavior — see coordination_manager) it integrates that velocity instead.
Lets the entire stack — UI included — be demonstrated with no hardware.
"""

from __future__ import annotations

import asyncio
import math
import time

from app.coordinate_transformer import GeoOrigin, gps_to_enu, normalize_angle_rad
from app.fault_injection import fault_injection_registry
from app.models import (
    BatteryState,
    GPSState,
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

# Arbitrary but realistic reference origin (used only to synthesize a
# plausible lat/lon for the UI's geographic map mode).
SIM_ORIGIN = GeoOrigin(latitude=37.4275, longitude=-122.1697)

COMMAND_FRESH_WINDOW_S = 1.0
CIRCLE_RADIUS_M = 3.0
CIRCLE_ANGULAR_RATE_RADPS = 0.12
CRUISE_ALT_M = 8.0


class MockDroneAdapter(RobotAdapter):
    def __init__(self, robot_id: str, display_name: str = "Simulated UAV") -> None:
        self.robot_id = robot_id
        self.display_name = display_name
        self._connected = False
        self._x = CIRCLE_RADIUS_M
        self._y = 0.0
        self._yaw = math.pi / 2
        self._battery_pct = 100.0
        self._last_command: RobotCommand | None = None
        self._task: asyncio.Task | None = None
        self._start_time = time.time()
        self._state = self._build_state()

    async def connect(self) -> RobotRegistration:
        self._connected = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._run())
        return RobotRegistration(
            robot_id=self.robot_id,
            robot_type=RobotType.UAV,
            protocol=Protocol.MOCK,
            display_name=self.display_name,
            capabilities=[
                RobotCapability.GPS,
                RobotCapability.ALTITUDE,
                RobotCapability.ATTITUDE,
                RobotCapability.BATTERY,
                RobotCapability.LINEAR_VELOCITY_CONTROL,
                RobotCapability.FLIGHT_MODE,
                RobotCapability.ARM,
                RobotCapability.DISARM,
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
        self._last_command = command

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

        following_active = (
            self._last_command is not None
            and (time.time() * 1000 - self._last_command.issued_at_ms) < COMMAND_FRESH_WINDOW_S * 1000
        )

        if following_active:
            cmd = self._last_command
            assert cmd is not None
            self._x += cmd.linear_x * dt
            self._y += cmd.linear_y * dt
            if cmd.angular_z:
                self._yaw = normalize_angle_rad(self._yaw + cmd.angular_z * dt)
        else:
            t = time.time() - self._start_time
            self._x = CIRCLE_RADIUS_M * math.cos(CIRCLE_ANGULAR_RATE_RADPS * t)
            self._y = CIRCLE_RADIUS_M * math.sin(CIRCLE_ANGULAR_RATE_RADPS * t)
            self._yaw = normalize_angle_rad(CIRCLE_ANGULAR_RATE_RADPS * t + math.pi / 2)

        self._battery_pct = max(
            0.0, self._battery_pct - 0.01 * dt * fault.battery_drain_rate_multiplier
        )

    def _build_state(self) -> RobotState:
        fault = fault_injection_registry.get(self.robot_id)
        source_ts = now_ms()

        gps = None
        if not fault.gps_loss:
            lat = SIM_ORIGIN.latitude + (self._y / 111_320.0)
            lon = SIM_ORIGIN.longitude + (
                self._x / (111_320.0 * math.cos(math.radians(SIM_ORIGIN.latitude)))
            )
            lat, lon = fault_injection_registry.apply_gps_noise(self.robot_id, lat, lon)
            gps = GPSState(latitude=lat, longitude=lon, altitude=CRUISE_ALT_M, fix=3)

        connected = self._connected and not fault.forced_disconnect
        health = HealthState.NORMAL
        if not connected:
            health = HealthState.UNKNOWN
        elif self._battery_pct < 15 or fault.gps_loss:
            health = HealthState.WARNING

        received_ts = source_ts + int(fault.extra_latency_ms)

        return RobotState(
            robot_id=self.robot_id,
            robot_type=RobotType.UAV,
            protocol=Protocol.MOCK,
            connected=connected,
            mode="SIM_FOLLOWER" if self._last_command else "SIM_AUTO",
            health=health,
            pose=RobotPose(x=self._x, y=self._y, z=CRUISE_ALT_M, yaw=self._yaw),
            gps=gps,
            velocity=VelocityState(linear_x=0.0, linear_y=0.0),
            battery=BatteryState(percentage=self._battery_pct, voltage=12.6 * (self._battery_pct / 100.0 * 0.2 + 0.8)),
            source_timestamp_ms=source_ts,
            received_timestamp_ms=received_ts,
        )
