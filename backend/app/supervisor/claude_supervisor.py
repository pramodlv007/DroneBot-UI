"""Anthropic (Claude)-backed supervisor. Same contract as OpenAISupervisor."""

from __future__ import annotations

import json
import time
from typing import Any

from app.models import HealthState, RecommendedAction, SupervisorRecommendation

from .base import MissionSupervisor
from .openai_supervisor import _SYSTEM_PROMPT


class ClaudeSupervisor(MissionSupervisor):
    provider_name = "claude"

    def __init__(self, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic  # local import: optional dependency

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def analyze(self, context: dict[str, Any]) -> SupervisorRecommendation:
        start = time.perf_counter()
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=300,
                system=_SYSTEM_PROMPT + "\nRespond with ONLY the JSON object, no other text.",
                messages=[{"role": "user", "content": json.dumps(context, default=str)}],
            )
            text = response.content[0].text
            payload = json.loads(text)
            rec = SupervisorRecommendation(
                status=HealthState(payload.get("status", "UNKNOWN")),
                summary=payload.get("summary", ""),
                detected_issue=payload.get("detected_issue"),
                recommended_action=RecommendedAction(payload.get("recommended_action", "CONTINUE")),
                confidence=float(payload.get("confidence", 0.0)),
                reasoning_summary=payload.get("reasoning_summary", ""),
                provider=self.provider_name,
            )
        except Exception as exc:  # noqa: BLE001
            rec = SupervisorRecommendation(
                status=HealthState.UNKNOWN,
                summary=f"Supervisor unavailable: {exc}",
                recommended_action=RecommendedAction.CONTINUE,
                confidence=0.0,
                reasoning_summary="Claude supervisor call failed or returned malformed output.",
                provider=self.provider_name,
            )

        rec.latency_ms = (time.perf_counter() - start) * 1000.0
        return rec
