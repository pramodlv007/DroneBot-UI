"""
Real MAVLink/pymavlink UAV adapter. Normalizes GLOBAL_POSITION_INT,
LOCAL_POSITION_NED, ATTITUDE, VFR_HUD, SYS_STATUS, GPS_RAW_INT and HEARTBEAT
into RobotState. Reuses the GPS->ENU and NED->ENU conversions from
coordinate_transformer rather than the ad hoc math the legacy scripts had
duplicated eight times (see docs/audit.md).

pymavlink is a blocking/synchronous library, so this adapter runs its own
background thread reading `recv_match(blocking=True, timeout=...)` and
publishes normalized RobotState back into the asyncio event loop via
`loop.call_soon_threadsafe`. No other module in this codebase imports
pymavlink — that is the layering boundary this adapter exists to enforce.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time

from pymavlink import mavutil

from app.config import RobotConfig
from app.coordinate_transformer import (
    CoordinateTransformer,
    ned_to_enu,
    ned_yaw_to_enu_yaw,
)
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

HEARTBEAT_CONNECT_TIMEOUT_S = 10.0
STREAM_RATE_HZ = 10


class DroneAdapter(RobotAdapter):
    def __init__(self, robot_id: str, config: RobotConfig) -> None:
        self.robot_id = robot_id
        self.config = config
        self._master = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

        self._transformer = CoordinateTransformer()
        self._lock = threading.Lock()
        self._state = RobotState(
            robot_id=robot_id,
            robot_type=RobotType.UAV,
            protocol=Protocol.MAVLINK,
            connected=False,
            pose=RobotPose(),
        )
        # raw fields accumulated across message types before each RobotState build
        self._roll = 0.0
        self._pitch = 0.0
        self._yaw_enu = 0.0
        self._gps_fix = 0
        self._battery_v: float | None = None
        self._battery_pct: float | None = None
        self._mode = "UNKNOWN"
        self._last_position_source_ms = 0

    async def connect(self) -> RobotRegistration:
        self._loop = asyncio.get_running_loop()
        self._master = await self._loop.run_in_executor(None, self._blocking_connect)
        self._running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

        return RobotRegistration(
            robot_id=self.robot_id,
            robot_type=RobotType.UAV,
            protocol=Protocol.MAVLINK,
            display_name=self.config.display_name,
            capabilities=[RobotCapability(c) for c in self.config.capabilities],
            supported_commands=["velocity"],
        )

    def _blocking_connect(self):
        master = mavutil.mavlink_connection(self.config.connection, baud=self.config.baud or 57600)
        master.wait_heartbeat(timeout=HEARTBEAT_CONNECT_TIMEOUT_S)

        interval_us = int(1_000_000 / STREAM_RATE_HZ)
        for msg_id in (32, 30, 74, 1, 24):  # LOCAL_POSITION_NED, ATTITUDE, VFR_HUD, SYS_STATUS, GPS_RAW_INT
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                0,
                msg_id,
                interval_us,
                0, 0, 0, 0, 0,
            )
        return master

    async def disconnect(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._master = None
        with self._lock:
            self._state = self._state.model_copy(update={"connected": False})

    def get_state(self) -> RobotState:
        with self._lock:
            return self._state

    async def send_command(self, command: RobotCommand) -> None:
        """Follower-mode velocity command -> SET_POSITION_TARGET_LOCAL_NED
        velocity-only setpoint. Bounded by SafetyManager before this is
        ever called; this adapter does not re-derive limits."""
        if self._master is None:
            return
        master = self._master
        vx_ned = command.linear_y   # ENU y (North) -> NED x
        vy_ned = command.linear_x   # ENU x (East)  -> NED y
        await self._loop.run_in_executor(
            None,
            lambda: master.mav.set_position_target_local_ned_send(
                int(time.time() * 1000) & 0xFFFFFFFF,
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                0b0000111111000111,  # velocity-only mask
                0, 0, 0,
                vx_ned, vy_ned, 0,
                0, 0, 0,
                0, 0,
            ),
        )

    def _recv_loop(self) -> None:
        while self._running and self._master is not None:
            msg = self._master.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue
            self._handle_message(msg)

    def _handle_message(self, msg) -> None:
        msg_type = msg.get_type()
        source_ts = now_ms()

        if msg_type == "HEARTBEAT":
            self._mode = mavutil.mode_string_v10(msg) if hasattr(mavutil, "mode_string_v10") else str(msg.custom_mode)

        elif msg_type == "ATTITUDE":
            self._roll = msg.roll
            self._pitch = msg.pitch
            self._yaw_enu = ned_yaw_to_enu_yaw(msg.yaw)

        elif msg_type == "GPS_RAW_INT":
            self._gps_fix = msg.fix_type

        elif msg_type == "SYS_STATUS":
            self._battery_v = msg.voltage_battery / 1000.0
            if msg.battery_remaining >= 0:
                self._battery_pct = float(msg.battery_remaining)

        elif msg_type == "LOCAL_POSITION_NED":
            x_enu, y_enu, z_enu = ned_to_enu(msg.x, msg.y, msg.z)
            self._last_position_source_ms = source_ts
            self._publish_pose(x_enu, y_enu, z_enu, gps=None, source_ts=source_ts)
            return

        elif msg_type == "GLOBAL_POSITION_INT":
            lat = msg.lat / 1e7
            lon = msg.lon / 1e7
            alt = msg.relative_alt / 1000.0
            x_enu, y_enu, _ = self._transformer.gps_to_mission_frame(lat, lon, alt)
            gps = GPSState(latitude=lat, longitude=lon, altitude=alt, fix=self._gps_fix)
            self._last_position_source_ms = source_ts
            self._publish_pose(x_enu, y_enu, alt, gps=gps, source_ts=source_ts)
            return

        # Non-position messages: refresh the cached state's ancillary fields
        # without moving the position/timestamp.
        with self._lock:
            self._state = self._state.model_copy(update=self._ancillary_fields())

    def _ancillary_fields(self) -> dict:
        return {
            "connected": True,
            "mode": self._mode,
            "pose": self._state.pose.model_copy(update={"roll": self._roll, "pitch": self._pitch, "yaw": self._yaw_enu}),
            "battery": BatteryState(voltage=self._battery_v, percentage=self._battery_pct),
            "health": self._derive_health(),
        }

    def _publish_pose(self, x: float, y: float, z: float, gps: GPSState | None, source_ts: int) -> None:
        state = RobotState(
            robot_id=self.robot_id,
            robot_type=RobotType.UAV,
            protocol=Protocol.MAVLINK,
            connected=True,
            mode=self._mode,
            health=self._derive_health(),
            pose=RobotPose(x=x, y=y, z=z, roll=self._roll, pitch=self._pitch, yaw=self._yaw_enu),
            gps=gps,
            velocity=VelocityState(),
            battery=BatteryState(voltage=self._battery_v, percentage=self._battery_pct),
            source_timestamp_ms=source_ts,
            received_timestamp_ms=now_ms(),
        )
        with self._lock:
            self._state = state
        self._emit(state)

    def _derive_health(self) -> HealthState:
        if self._battery_pct is not None and self._battery_pct < 15:
            return HealthState.WARNING
        if self._gps_fix < 2:
            return HealthState.WARNING
        return HealthState.NORMAL
