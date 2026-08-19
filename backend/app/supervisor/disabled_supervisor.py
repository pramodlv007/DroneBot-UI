from __future__ import annotations

from typing import Any

from app.models import HealthState, RecommendedAction, SupervisorRecommendation

from .base import MissionSupervisor


class DisabledSupervisor(MissionSupervisor):
    """No-op supervisor: the system must function identically with AI
    disabled (§37, §48). Always returns a neutral, non-actionable status."""

    provider_name = "disabled"

    async def analyze(self, context: dict[str, Any]) -> SupervisorRecommendation:
        return SupervisorRecommendation(
            status=HealthState.UNKNOWN,
            summary="AI supervisor disabled.",
            recommended_action=RecommendedAction.CONTINUE,
            confidence=0.0,
            reasoning_summary="Supervisor provider is DisabledSupervisor.",
            provider=self.provider_name,
        )
