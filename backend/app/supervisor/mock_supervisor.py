"""
Deterministic, rule-based "supervisor" that mimics an LLM's structured
output without calling out to any model. Used for SIMULATION mode and for
tests, so the AI panel is always demonstrable offline (§29, §37).
"""

from __future__ import annotations

import time
from typing import Any

from app.models import HealthState, RecommendedAction, SupervisorRecommendation

from .base import MissionSupervisor


class MockSupervisor(MissionSupervisor):
    provider_name = "mock"

    async def analyze(self, context: dict[str, Any]) -> SupervisorRecommendation:
        start = time.perf_counter()

        tracking_error_m = (context.get("coordination") or {}).get("tracking_error_m")
        system_health = context.get("system_health")

        if tracking_error_m is not None and tracking_error_m > 2.0:
            rec = SupervisorRecommendation(
                status=HealthState.WARNING,
                summary=f"Tracking error is elevated ({tracking_error_m:.2f} m).",
                detected_issue="FOLLOWER_LAG",
                recommended_action=RecommendedAction.SLOW_DOWN,
                confidence=0.8,
                reasoning_summary="Tracking error exceeded the degraded threshold in the latest sample.",
                provider=self.provider_name,
            )
        elif system_health == HealthState.CRITICAL:
            rec = SupervisorRecommendation(
                status=HealthState.CRITICAL,
                summary="System health is critical.",
                detected_issue="SYSTEM_HEALTH_CRITICAL",
                recommended_action=RecommendedAction.RETURN_TO_SAFE_STATE,
                confidence=0.9,
                reasoning_summary="A robot or subsystem reported CRITICAL health.",
                provider=self.provider_name,
            )
        else:
            rec = SupervisorRecommendation(
                status=HealthState.NORMAL,
                summary="Tracking stable and system health nominal.",
                recommended_action=RecommendedAction.CONTINUE,
                confidence=0.95,
                reasoning_summary="No thresholds exceeded in the latest telemetry sample.",
                provider=self.provider_name,
            )

        rec.latency_ms = (time.perf_counter() - start) * 1000.0
        return rec
