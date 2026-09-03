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
import threading
import time

from pymavlink import mavutil

from app.config import RobotConfig
from app.coordinate_transformer import (
    CoordinateTransformer,
    ned_to_enu,
    ned_yaw_to_enu_yaw,
)
from app.dead_reckoning import DeadReckoningEstimator
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
        self._last_real_position_ms = 0
        self._last_alt_m = 0.0

        # Indoor/GPS-denied fallback: integrates heading (yaw) + ground
        # speed (VFR_HUD) forward through time when there is no usable GPS
        # fix. Opt-in — see set_dead_reckoning() — and always tagged in
        # RobotState.metadata so the UI never shows it as real GPS/EKF truth.
        self._dr_enabled = False
        self._dr_active = False
        self._dead_reckoning = DeadReckoningEstimator()
        self._vfr_groundspeed = 0.0
        self._last_emit_ms = 0

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
        master = mavutil.mavlink_connection(
            self.config.connection,
            baud=self.config.baud or 57600,
        )
        try:
            master.wait_heartbeat(timeout=HEARTBEAT_CONNECT_TIMEOUT_S)
        except Exception:
            # Always close the serial handle before re-raising so the OS
            # port lock is released and a subsequent CONNECT attempt won't
            # see "Permission denied" / "Access is denied".
            try:
                master.close()
            except Exception:
                pass
            raise

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
        if self._master is not None:
            try:
                self._master.close()  # release the OS serial port handle immediately so read unblocks
            except Exception:
                pass
            self._master = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
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
            try:
                msg = self._master.recv_match(blocking=True, timeout=0.5)
            except Exception:
                break
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
            had_fix = self._gps_fix >= 2
            self._gps_fix = msg.fix_type
            has_fix = self._gps_fix >= 2
            if had_fix and not has_fix and self._dr_enabled:
                # GPS just dropped — seed dead reckoning from the last
                # known-good position instead of jumping to (0, 0).
                self._dead_reckoning.seed(self._state.pose.x, self._state.pose.y)

        elif msg_type == "VFR_HUD":
            self._vfr_groundspeed = msg.groundspeed
            # Only fall back to dead reckoning when there is no GPS fix AND
            # no real position source (LOCAL_POSITION_NED) has reported in
            # recently — real telemetry always wins when it's available.
            no_recent_real_position = (source_ts - self._last_real_position_ms) > 500
            if self._dr_enabled and self._gps_fix < 2 and no_recent_real_position:
                dr_x, dr_y = self._dead_reckoning.update(self._yaw_enu, self._vfr_groundspeed, source_ts)
                self._last_position_source_ms = source_ts
                self._publish_pose(dr_x, dr_y, self._last_alt_m, gps=None, source_ts=source_ts, dead_reckoning=True)
                return

        elif msg_type == "SYS_STATUS":
            self._battery_v = msg.voltage_battery / 1000.0
            if msg.battery_remaining >= 0:
                self._battery_pct = float(msg.battery_remaining)

        elif msg_type == "LOCAL_POSITION_NED":
            x_enu, y_enu, z_enu = ned_to_enu(msg.x, msg.y, msg.z)
            self._last_position_source_ms = source_ts
            self._last_real_position_ms = source_ts
            self._last_alt_m = z_enu
            self._publish_pose(x_enu, y_enu, z_enu, gps=None, source_ts=source_ts)
            return

        elif msg_type == "GLOBAL_POSITION_INT":
            alt = msg.relative_alt / 1000.0
            self._last_alt_m = alt
            if self._gps_fix >= 2:
                lat = msg.lat / 1e7
                lon = msg.lon / 1e7
                x_enu, y_enu, _ = self._transformer.gps_to_mission_frame(lat, lon, alt)
                gps = GPSState(latitude=lat, longitude=lon, altitude=alt, fix=self._gps_fix)
                self._last_position_source_ms = source_ts
                self._last_real_position_ms = source_ts
                self._publish_pose(x_enu, y_enu, alt, gps=gps, source_ts=source_ts, dead_reckoning=False)
                return
            # No usable GPS fix: don't trust lat/lon from this message.
            # Fall through to the ancillary-field refresh below so mode/
            # battery/health still update; position is left to
            # LOCAL_POSITION_NED or VFR_HUD-driven dead reckoning instead.

        # Non-position messages (ATTITUDE, HEARTBEAT, SYS_STATUS, etc.):
        # refresh the cached state's ancillary fields, update timestamps,
        # and emit periodically (>= 10Hz) so the gateway watchdog and UI
        # receive live telemetry even when indoors / waiting for GPS lock.
        now = now_ms()
        fields = self._ancillary_fields()
        fields["source_timestamp_ms"] = source_ts
        fields["received_timestamp_ms"] = now
        with self._lock:
            self._state = self._state.model_copy(update=fields)
            state_to_emit = self._state

        if (now - self._last_emit_ms) >= 100:
            self._last_emit_ms = now
            self._emit(state_to_emit)

    def _ancillary_fields(self) -> dict:
        return {
            "connected": True,
            "mode": self._mode,
            "pose": self._state.pose.model_copy(update={"roll": self._roll, "pitch": self._pitch, "yaw": self._yaw_enu}),
            "battery": BatteryState(voltage=self._battery_v, percentage=self._battery_pct),
            "health": self._derive_health(),
            "metadata": {"dead_reckoning_active": self._dr_active},
        }

    def _publish_pose(
        self, x: float, y: float, z: float, gps: GPSState | None, source_ts: int, dead_reckoning: bool = False
    ) -> None:
        self._dr_active = dead_reckoning
        state = RobotState(
            robot_id=self.robot_id,
            robot_type=RobotType.UAV,
            protocol=Protocol.MAVLINK,
            connected=True,
            mode=self._mode,
            health=self._derive_health(),
            pose=RobotPose(x=x, y=y, z=z, roll=self._roll, pitch=self._pitch, yaw=self._yaw_enu),
            gps=gps,
            velocity=VelocityState(linear_x=self._vfr_groundspeed if dead_reckoning else 0.0),
            battery=BatteryState(voltage=self._battery_v, percentage=self._battery_pct),
            source_timestamp_ms=source_ts,
            received_timestamp_ms=now_ms(),
            metadata={"dead_reckoning_active": dead_reckoning},
        )
        with self._lock:
            self._state = state
        self._last_emit_ms = now_ms()
        self._emit(state)

    def _derive_health(self) -> HealthState:
        if self._battery_pct is not None and self._battery_pct < 15:
            return HealthState.WARNING
        if self._gps_fix < 2:
            return HealthState.WARNING
        return HealthState.NORMAL

    # -- indoor/GPS-denied dead reckoning --------------------------------

    def set_dead_reckoning(self, enabled: bool) -> None:
        """Operator-controlled opt-in. Enabling seeds the estimator from the
        current pose so it continues from reality rather than (0, 0)."""
        self._dr_enabled = enabled
        if enabled:
            self._dead_reckoning.seed(self._state.pose.x, self._state.pose.y)
        else:
            self._dr_active = False

    def reset_dead_reckoning_origin(self) -> None:
        """Re-zero the drift-accumulating estimate at the current position —
        use this when the vehicle is back at a known reference point."""
        self._dead_reckoning.seed(self._state.pose.x, self._state.pose.y)

    @property
    def dead_reckoning_enabled(self) -> bool:
        return self._dr_enabled

    @property
    def dead_reckoning_active(self) -> bool:
        """True only while dead reckoning is actually substituting for a
        missing real position source right now (not just toggled on)."""
        return self._dr_active
