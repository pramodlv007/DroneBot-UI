"""
Enhanced Simulated UAV adapter with a scripted scenario cycle so the
AI Monitor tab sees interesting, varied data during development/testing.

Scenario cycle (repeats every ~120 s):
  Phase 0 — 0-15 s:   All nominal. Circular flight, battery ~95%, good GPS.
  Phase 1 — 15-30 s:  Battery warning zone (drains fast to 28 %).
  Phase 2 — 30-45 s:  GPS degraded (fix drops to 1) — simulates indoor entry.
  Phase 3 — 45-60 s:  High telemetry lag injected (350 ms).
  Phase 4 — 60-75 s:  Drone stalls — velocity zeroed while mission is RUNNING.
  Phase 5 — 75-90 s:  Unexpected flight mode (LOITER during RUNNING mission).
  Phase 6 — 90-105 s: Battery critical (12 %) + GPS restored.
  Phase 7 — 105-120 s: Recovery — all back to nominal, battery starts reset.
"""

from __future__ import annotations

import asyncio
import math
import time

from app.coordinate_transformer import GeoOrigin, normalize_angle_rad
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

SIM_ORIGIN = GeoOrigin(latitude=37.4275, longitude=-122.1697)

COMMAND_FRESH_WINDOW_S = 1.0
CIRCLE_RADIUS_M = 3.0
CIRCLE_ANGULAR_RATE_RADPS = 0.12
CRUISE_ALT_M = 8.0

SCENARIO_CYCLE_S = 120.0  # total cycle duration


def _phase(t: float) -> int:
    """Return 0-7 based on position within the 120 s cycle."""
    t = t % SCENARIO_CYCLE_S
    if t < 15:   return 0   # nominal
    if t < 30:   return 1   # battery warning
    if t < 45:   return 2   # GPS degraded
    if t < 60:   return 3   # high latency
    if t < 75:   return 4   # drone stall
    if t < 90:   return 5   # unexpected flight mode
    if t < 105:  return 6   # battery critical
    return 7                 # recovery


class MockDroneAdapter(RobotAdapter):
    def __init__(self, robot_id: str, display_name: str = "Simulated UAV") -> None:
        self.robot_id = robot_id
        self.display_name = display_name
        self._connected = False
        self._x = CIRCLE_RADIUS_M
        self._y = 0.0
        self._yaw = math.pi / 2
        self._battery_pct = 95.0
        self._last_command: RobotCommand | None = None
        self._task: asyncio.Task | None = None
        self._start_time = time.time()
        self._dr_enabled = False
        self._state = self._build_state()

    def set_dead_reckoning(self, enabled: bool) -> None:
        self._dr_enabled = enabled

    def reset_dead_reckoning_origin(self) -> None:
        pass

    @property
    def dead_reckoning_enabled(self) -> bool:
        return self._dr_enabled

    async def connect(self) -> RobotRegistration:
        self._connected = True
        self._start_time = time.time()
        self._battery_pct = 95.0
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
        t = time.time() - self._start_time
        phase = _phase(t)

        following_active = (
            self._last_command is not None
            and (time.time() * 1000 - self._last_command.issued_at_ms) < COMMAND_FRESH_WINDOW_S * 1000
        )

        # Phase 4 = stall: don't move even if following
        if phase == 4:
            pass  # position frozen
        elif following_active:
            cmd = self._last_command
            assert cmd is not None
            self._x += cmd.linear_x * dt
            self._y += cmd.linear_y * dt
            if cmd.angular_z:
                self._yaw = normalize_angle_rad(self._yaw + cmd.angular_z * dt)
        else:
            self._x = CIRCLE_RADIUS_M * math.cos(CIRCLE_ANGULAR_RATE_RADPS * t)
            self._y = CIRCLE_RADIUS_M * math.sin(CIRCLE_ANGULAR_RATE_RADPS * t)
            self._yaw = normalize_angle_rad(CIRCLE_ANGULAR_RATE_RADPS * t + math.pi / 2)

        # Scenario-driven battery drain rates
        drain_rates = {
            0: 0.02,   # nominal — gentle drain
            1: 1.5,    # phase 1: fast drain to hit warning
            2: 0.05,
            3: 0.05,
            4: 0.05,
            5: 0.05,
            6: 2.0,    # phase 6: drain to critical
            7: -1.0,   # recovery: recharge (clamp at 95)
        }
        rate = drain_rates.get(phase, 0.02)
        self._battery_pct = max(0.0, min(95.0, self._battery_pct - rate * dt * fault.battery_drain_rate_multiplier))

    def _build_state(self) -> RobotState:
        fault = fault_injection_registry.get(self.robot_id)
        t = time.time() - self._start_time
        phase = _phase(t)

        source_ts = now_ms()

        # GPS: degrade in phases 2
        gps = None
        if not fault.gps_loss:
            lat = SIM_ORIGIN.latitude + (self._y / 111_320.0)
            lon = SIM_ORIGIN.longitude + (
                self._x / (111_320.0 * math.cos(math.radians(SIM_ORIGIN.latitude)))
            )
            lat, lon = fault_injection_registry.apply_gps_noise(self.robot_id, lat, lon)
            gps_fix = 1 if phase == 2 else 3   # weak fix in phase 2
            gps = GPSState(latitude=lat, longitude=lon, altitude=CRUISE_ALT_M, fix=gps_fix)

        # Flight mode: unexpected LOITER in phase 5
        mode_map = {
            0: "SIM_AUTO",
            1: "SIM_AUTO",
            2: "SIM_AUTO",
            3: "SIM_AUTO",
            4: "SIM_HOVER",  # hovering in place (stall)
            5: "LOITER",     # unexpected — should be AUTO during mission
            6: "SIM_AUTO",
            7: "SIM_AUTO",
        }
        mode = mode_map.get(phase, "SIM_AUTO")
        if self._last_command:
            mode = "SIM_FOLLOWER"

        # Telemetry lag: inject 350 ms in phase 3
        base_lag = int(fault.extra_latency_ms)
        extra_lag = 350 if phase == 3 else 0
        received_ts = source_ts + base_lag + extra_lag

        connected = self._connected and not fault.forced_disconnect
        health = HealthState.NORMAL
        if not connected:
            health = HealthState.UNKNOWN
        elif self._battery_pct < 15 or fault.gps_loss or phase == 2:
            health = HealthState.WARNING
        elif self._battery_pct < 30:
            health = HealthState.WARNING

        # Roll/pitch to simulate realistic attitude during flight
        roll_rad = 0.05 * math.sin(CIRCLE_ANGULAR_RATE_RADPS * t * 2)
        pitch_rad = 0.03 * math.cos(CIRCLE_ANGULAR_RATE_RADPS * t * 3)

        return RobotState(
            robot_id=self.robot_id,
            robot_type=RobotType.UAV,
            protocol=Protocol.MOCK,
            connected=connected,
            mode=mode,
            health=health,
            pose=RobotPose(
                x=self._x, y=self._y, z=CRUISE_ALT_M,
                roll=roll_rad, pitch=pitch_rad, yaw=self._yaw,
            ),
            gps=gps,
            velocity=VelocityState(
                linear_x=0.0 if phase == 4 else CIRCLE_RADIUS_M * CIRCLE_ANGULAR_RATE_RADPS * math.sin(CIRCLE_ANGULAR_RATE_RADPS * t),
                linear_y=0.0 if phase == 4 else CIRCLE_RADIUS_M * CIRCLE_ANGULAR_RATE_RADPS * math.cos(CIRCLE_ANGULAR_RATE_RADPS * t),
            ),
            battery=BatteryState(
                percentage=self._battery_pct,
                voltage=12.6 * (self._battery_pct / 100.0 * 0.2 + 0.8),
            ),
            source_timestamp_ms=source_ts,
            received_timestamp_ms=received_ts,
            # Matches the real DroneAdapter's gating: active whenever there's
            # no usable GPS fix (lost entirely via the "GPS Loss" fault, or
            # degraded below fix=2 by the phase-2 "indoor entry" scenario)
            # and the operator has opted in.
            metadata={"dead_reckoning_active": self._dr_enabled and not (gps is not None and gps.fix >= 2), "sim_phase": phase},
        )
