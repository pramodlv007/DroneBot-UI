"""
Simulated fault injection for SIMULATION/TEST deployment modes (§50).

This module is imported by mock adapters only. It is intentionally NOT
wired into any real adapter — the API layer (routers/robots_api.py) refuses
fault-injection requests outright unless `settings.deployment_mode !=
"PHYSICAL"`, so there is no code path by which a fault can be injected
against a real robot connection.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class FaultProfile:
    extra_latency_ms: float = 0.0
    packet_loss_pct: float = 0.0       # 0-100
    gps_noise_std_m: float = 0.0
    gps_loss: bool = False
    odometry_freeze: bool = False
    battery_drain_rate_multiplier: float = 1.0
    forced_disconnect: bool = False
    tracking_disturbance_m: float = 0.0


class FaultInjectionRegistry:
    """In-memory, per-robot fault profiles. Reset on process restart —
    this is a research/demo tool, not persisted state."""

    def __init__(self) -> None:
        self._profiles: dict[str, FaultProfile] = {}

    def get(self, robot_id: str) -> FaultProfile:
        return self._profiles.setdefault(robot_id, FaultProfile())

    def set(self, robot_id: str, profile: FaultProfile) -> None:
        self._profiles[robot_id] = profile

    def clear(self, robot_id: str) -> None:
        self._profiles[robot_id] = FaultProfile()

    def should_drop_packet(self, robot_id: str) -> bool:
        profile = self.get(robot_id)
        if profile.packet_loss_pct <= 0:
            return False
        return random.uniform(0, 100) < profile.packet_loss_pct

    def apply_gps_noise(self, robot_id: str, lat: float, lon: float) -> tuple[float, float]:
        profile = self.get(robot_id)
        if profile.gps_noise_std_m <= 0:
            return lat, lon
        # ~1 degree latitude ≈ 111,320 m; small-noise approximation is fine here.
        deg_std = profile.gps_noise_std_m / 111_320.0
        return lat + random.gauss(0, deg_std), lon + random.gauss(0, deg_std)


fault_injection_registry = FaultInjectionRegistry()
