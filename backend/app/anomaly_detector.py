"""
Anomaly Detector — always-on sliding-window checks over live telemetry,
run once per control-loop tick regardless of which UI panel (if any) is
open. This is deliberately separate from the AI Monitor's rule engine
(app/routers/ai_monitor_api.py), which only evaluates when the frontend
polls it — a stuck robot or a runaway battery drain shouldn't depend on an
operator having a particular browser tab open to be noticed.

Checks (see AnomalyConfig for thresholds):
  STUCK               — robot has been continuously, non-trivially
                         commanded for stuck_window_s but has displaced
                         less than stuck_distance_m. Only meaningful for
                         the coordination manager's active follower, since
                         that's the only robot we actually command.
  BATTERY_DRAIN       — battery percentage fell by more than
                         battery_drop_pct within battery_window_s — faster
                         than any normal mission profile, so treat it as a
                         possible fault rather than expected discharge.
  POSITION_JUMP       — implied speed between two consecutive telemetry
                         samples exceeds physical plausibility: a sensor
                         glitch, EKF reset, or bad dead-reckoning
                         integration, not a genuine maneuver.
  HEADING_OSCILLATION — yaw-rate keeps reversing direction within a short
                         window, suggesting an unstable controller or a
                         noisy heading estimate rather than an intentional
                         turn.

Each check keeps its own per-robot ring buffer and applies a cooldown so a
persistent condition emits one event, not one every tick.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from app.config import AnomalyConfig
from app.coordinate_transformer import normalize_angle_rad
from app.models import EventSeverity, MissionEvent, RobotCommand, RobotState

# Long enough to cover the longest configured window (battery, by default)
# at a 10Hz control loop, with headroom for a slower configured rate.
_HISTORY_MAXLEN = 600


@dataclass
class _Sample:
    ts_ms: int
    x: float
    y: float
    yaw: float
    battery_pct: float | None
    command_active: bool


@dataclass
class _RobotTrack:
    samples: deque[_Sample] = field(default_factory=lambda: deque(maxlen=_HISTORY_MAXLEN))
    last_fired_ms: dict[str, int] = field(default_factory=dict)
    stuck_active: bool = False
    oscillation_active: bool = False


class AnomalyDetector:
    def __init__(self, config: AnomalyConfig) -> None:
        self.cfg = config
        self._tracks: dict[str, _RobotTrack] = {}

    def evaluate(
        self,
        now_ms: int,
        robot_states: dict[str, RobotState],
        active_command: RobotCommand | None,
        mission_running: bool,
    ) -> list[MissionEvent]:
        if not self.cfg.enabled:
            return []

        events: list[MissionEvent] = []
        seen_ids = set(robot_states.keys())
        for stale_id in set(self._tracks) - seen_ids:
            del self._tracks[stale_id]

        for robot_id, state in robot_states.items():
            if not state.connected:
                # Drop history on disconnect so a reconnect doesn't compare
                # against a stale pre-disconnect window.
                self._tracks.pop(robot_id, None)
                continue

            track = self._tracks.setdefault(robot_id, _RobotTrack())
            command_active = (
                active_command is not None
                and active_command.robot_id == robot_id
                and (
                    abs(active_command.linear_x) >= self.cfg.stuck_command_threshold
                    or abs(active_command.angular_z) >= self.cfg.stuck_command_threshold
                )
            )
            track.samples.append(
                _Sample(
                    ts_ms=now_ms,
                    x=state.pose.x,
                    y=state.pose.y,
                    yaw=state.pose.yaw,
                    battery_pct=state.battery.percentage if state.battery else None,
                    command_active=command_active,
                )
            )

            events += self._check_position_jump(robot_id, track)
            events += self._check_battery_drain(robot_id, track)
            if mission_running:
                events += self._check_stuck(robot_id, track)
                events += self._check_heading_oscillation(robot_id, track)

        return events

    def active_anomalies(self) -> dict[str, list[str]]:
        """Current *ongoing* anomaly conditions per robot — only STUCK and
        HEADING_OSCILLATION have real sustained on/off state; a battery-drop
        or position-jump is a point-in-time detection with no meaningful
        "still happening" flag, so they're reported as events only (see
        evaluate()), not surfaced here. Only robots with at least one active
        condition are included."""
        result: dict[str, list[str]] = {}
        for robot_id, track in self._tracks.items():
            active = []
            if track.stuck_active:
                active.append("STUCK")
            if track.oscillation_active:
                active.append("HEADING_OSCILLATION")
            if active:
                result[robot_id] = active
        return result

    def _cooldown_ok(self, track: _RobotTrack, kind: str, now_ms: int) -> bool:
        last = track.last_fired_ms.get(kind)
        return last is None or (now_ms - last) >= self.cfg.cooldown_s * 1000

    def _check_position_jump(self, robot_id: str, track: _RobotTrack) -> list[MissionEvent]:
        samples = track.samples
        if len(samples) < 2:
            return []
        prev, curr = samples[-2], samples[-1]
        dt_s = (curr.ts_ms - prev.ts_ms) / 1000.0
        if dt_s <= 0:
            return []
        dist = math.hypot(curr.x - prev.x, curr.y - prev.y)
        implied_speed = dist / dt_s
        if implied_speed <= self.cfg.position_jump_max_speed_mps:
            return []
        if not self._cooldown_ok(track, "POSITION_JUMP", curr.ts_ms):
            return []
        track.last_fired_ms["POSITION_JUMP"] = curr.ts_ms
        return [
            MissionEvent(
                type="ANOMALY_POSITION_JUMP",
                severity=EventSeverity.WARNING,
                robot_ids=[robot_id],
                message=(
                    f"{robot_id} position jumped {dist:.2f} m in {dt_s * 1000:.0f} ms "
                    f"(~{implied_speed:.1f} m/s) — possible GPS/EKF glitch"
                ),
                value=implied_speed,
            )
        ]

    def _check_stuck(self, robot_id: str, track: _RobotTrack) -> list[MissionEvent]:
        samples = track.samples
        if not samples or not samples[-1].command_active:
            track.stuck_active = False
            return []
        now = samples[-1].ts_ms
        window_ms = self.cfg.stuck_window_s * 1000
        if (now - samples[0].ts_ms) < window_ms:
            return []  # not enough history buffered yet

        window_start = now - window_ms
        windowed = [s for s in samples if s.ts_ms >= window_start]
        if not all(s.command_active for s in windowed):
            # Command only recently became continuous — wait for a full window of it.
            track.stuck_active = False
            return []

        oldest = windowed[0]
        dist = math.hypot(samples[-1].x - oldest.x, samples[-1].y - oldest.y)
        if dist > self.cfg.stuck_distance_m:
            if track.stuck_active:
                track.stuck_active = False
                return [
                    MissionEvent(
                        type="ANOMALY_STUCK_RECOVERED",
                        severity=EventSeverity.INFO,
                        robot_ids=[robot_id],
                        message=f"{robot_id} moving again after a stuck condition",
                    )
                ]
            return []

        if not self._cooldown_ok(track, "STUCK", now):
            return []
        track.last_fired_ms["STUCK"] = now
        track.stuck_active = True
        return [
            MissionEvent(
                type="ANOMALY_STUCK",
                severity=EventSeverity.WARNING,
                robot_ids=[robot_id],
                message=(
                    f"{robot_id} commanded to move but has only displaced {dist * 100:.1f} cm "
                    f"in {self.cfg.stuck_window_s:.0f}s — possible obstacle, wheel slip, or stall"
                ),
                value=dist,
            )
        ]

    def _check_heading_oscillation(self, robot_id: str, track: _RobotTrack) -> list[MissionEvent]:
        samples = track.samples
        if len(samples) < 3:
            return []
        now = samples[-1].ts_ms
        window_start = now - self.cfg.heading_oscillation_window_s * 1000
        windowed = [s for s in samples if s.ts_ms >= window_start]
        if len(windowed) < 3:
            return []

        rates: list[float] = []
        for prev, curr in zip(windowed, list(windowed)[1:]):
            dt_s = (curr.ts_ms - prev.ts_ms) / 1000.0
            if dt_s <= 0:
                continue
            dyaw = normalize_angle_rad(curr.yaw - prev.yaw)
            rates.append(dyaw / dt_s)

        significant = [r for r in rates if abs(r) >= self.cfg.heading_oscillation_min_rate_radps]
        flips = sum(1 for a, b in zip(significant, significant[1:]) if (a > 0) != (b > 0))

        if flips < self.cfg.heading_oscillation_min_flips:
            if track.oscillation_active:
                track.oscillation_active = False
                return [
                    MissionEvent(
                        type="ANOMALY_HEADING_STABLE",
                        severity=EventSeverity.INFO,
                        robot_ids=[robot_id],
                        message=f"{robot_id} heading stabilized",
                    )
                ]
            return []

        if not self._cooldown_ok(track, "HEADING_OSCILLATION", now):
            return []
        track.last_fired_ms["HEADING_OSCILLATION"] = now
        track.oscillation_active = True
        return [
            MissionEvent(
                type="ANOMALY_HEADING_OSCILLATION",
                severity=EventSeverity.WARNING,
                robot_ids=[robot_id],
                message=(
                    f"{robot_id} heading oscillating ({flips} direction reversals in "
                    f"{self.cfg.heading_oscillation_window_s:.0f}s) — possible control "
                    "instability or noisy heading estimate"
                ),
                value=float(flips),
            )
        ]

    def _check_battery_drain(self, robot_id: str, track: _RobotTrack) -> list[MissionEvent]:
        samples = track.samples
        if not samples or samples[-1].battery_pct is None:
            return []
        now = samples[-1].ts_ms
        window_ms = self.cfg.battery_window_s * 1000
        windowed = [s for s in samples if s.ts_ms >= now - window_ms and s.battery_pct is not None]
        # Require the window to be nearly full before judging a drop, so a
        # robot that just connected (or whose battery reporting just
        # resumed) doesn't get compared against a synthetic short window.
        if len(windowed) < 2 or (now - windowed[0].ts_ms) < window_ms * 0.8:
            return []

        drop = windowed[0].battery_pct - samples[-1].battery_pct  # type: ignore[operator]
        if drop < self.cfg.battery_drop_pct:
            return []
        if not self._cooldown_ok(track, "BATTERY_DRAIN", now):
            return []
        track.last_fired_ms["BATTERY_DRAIN"] = now
        current_pct = samples[-1].battery_pct or 0.0
        return [
            MissionEvent(
                type="ANOMALY_BATTERY_DRAIN",
                severity=EventSeverity.CRITICAL if current_pct < 30 else EventSeverity.WARNING,
                robot_ids=[robot_id],
                message=(
                    f"{robot_id} battery dropped {drop:.1f}% in {self.cfg.battery_window_s:.0f}s "
                    f"({windowed[0].battery_pct:.0f}% → {current_pct:.0f}%) — faster than expected"
                ),
                value=drop,
            )
        ]
