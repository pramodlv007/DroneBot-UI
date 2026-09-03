"""
Dead-reckoning position estimator — the UAV's fallback for indoor/GPS-denied
flight, where GLOBAL_POSITION_INT/LOCAL_POSITION_NED never arrive (or arrive
with a useless fix) because there is no GPS lock.

This is *not* a substitute for real position data: it integrates the
flight controller's own reported heading (yaw, from ATTITUDE) and ground
speed (from VFR_HUD) forward through time — classic dead reckoning. Like
any inertial-only estimate it accumulates drift with no bound, so it is
opt-in per robot, always tagged in RobotState.metadata so the UI can badge
it, and exposed with a manual reset so an operator can re-zero it against a
known point (e.g. a marked spot on the floor) whenever drift matters.
"""

from __future__ import annotations

import math


class DeadReckoningEstimator:
    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self._last_ts_ms: int | None = None

    def seed(self, x: float, y: float) -> None:
        """Re-zero the estimate at a known (or last-known-good) position.
        Called on enable, on manual reset, and automatically the moment GPS
        fix is lost so the estimate continues from reality instead of
        jumping back to (0, 0)."""
        self.x = x
        self.y = y
        self._last_ts_ms = None  # next update() establishes a fresh dt baseline

    def update(self, yaw_rad: float, ground_speed_mps: float, timestamp_ms: int) -> tuple[float, float]:
        """Integrate one tick of heading + ground speed. Returns the updated
        (x, y) estimate in the same ENU mission frame as RobotPose."""
        if self._last_ts_ms is None:
            self._last_ts_ms = timestamp_ms
            return self.x, self.y

        dt = (timestamp_ms - self._last_ts_ms) / 1000.0
        self._last_ts_ms = timestamp_ms

        # Guard against negative/huge dt (out-of-order packets, a long pause
        # between messages) rather than letting one bad sample fling the
        # estimate across the map.
        if dt <= 0 or dt > 1.0:
            return self.x, self.y

        self.x += ground_speed_mps * math.cos(yaw_rad) * dt
        self.y += ground_speed_mps * math.sin(yaw_rad) * dt
        return self.x, self.y
