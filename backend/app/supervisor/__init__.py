from __future__ import annotations

from app.config import Settings

from .base import MissionSupervisor
from .disabled_supervisor import DisabledSupervisor
from .mock_supervisor import MockSupervisor


def build_supervisor(settings: Settings) -> MissionSupervisor:
    provider = settings.supervisor.provider.lower()

    if provider == "openai" and settings.openai_api_key:
        from .openai_supervisor import OpenAISupervisor

        return OpenAISupervisor(api_key=settings.openai_api_key, model=settings.openai_model)

    if provider == "claude" and settings.anthropic_api_key:
        from .claude_supervisor import ClaudeSupervisor

        return ClaudeSupervisor(api_key=settings.anthropic_api_key, model=settings.anthropic_model)

    if provider == "mock":
        return MockSupervisor()

    return DisabledSupervisor()
