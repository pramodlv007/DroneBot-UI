"""
MissionSupervisor interface (§22, §47). Every provider (Mock/Disabled/
OpenAI/Claude) implements `analyze()` and returns a SupervisorRecommendation
— never a raw command. The rest of the system does not know or care which
provider is active.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models import SupervisorRecommendation


class SupervisorContext(dict):
    """Structured input to the supervisor: robot telemetry, coordination
    state, mission state, health state, and recent experiment/event
    context. Just a typed alias over dict for now — see
    websocket.py/main.py for what's populated into it."""


class MissionSupervisor(ABC):
    provider_name: str = "unknown"

    @abstractmethod
    async def analyze(self, context: dict[str, Any]) -> SupervisorRecommendation:
        ...
