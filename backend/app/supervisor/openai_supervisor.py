"""
OpenAI-backed supervisor. Structured-output prompt closely follows §22 —
the model is explicitly instructed never to emit actuator-level values,
and validator.py double-checks that regardless of what the model returns.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.models import HealthState, RecommendedAction, SupervisorRecommendation

from .base import MissionSupervisor

_SYSTEM_PROMPT = """You are a robotics mission supervisor for a heterogeneous \
aerial-ground robot team. You analyze telemetry and coordination state and \
return a structured recommendation for a human operator.

You must NEVER output raw motor commands, velocities, PWM values, or any \
actuator-level instruction. You only classify mission health and suggest one \
of a fixed set of high-level actions.

Respond with strict JSON matching this schema:
{
  "status": "NORMAL" | "WARNING" | "CRITICAL" | "UNKNOWN",
  "summary": string,
  "detected_issue": string | null,
  "recommended_action": "CONTINUE" | "SLOW_DOWN" | "PAUSE" | "STOP" | "CHECK_GPS" | "CHECK_COMMUNICATION" | "RETURN_TO_SAFE_STATE",
  "confidence": number between 0 and 1,
  "reasoning_summary": string
}"""


class OpenAISupervisor(MissionSupervisor):
    provider_name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI  # local import: optional dependency

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def analyze(self, context: dict[str, Any]) -> SupervisorRecommendation:
        start = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(context, default=str)},
                ],
                response_format={"type": "json_object"},
                max_tokens=300,
            )
            payload = json.loads(response.choices[0].message.content)
            rec = SupervisorRecommendation(
                status=HealthState(payload.get("status", "UNKNOWN")),
                summary=payload.get("summary", ""),
                detected_issue=payload.get("detected_issue"),
                recommended_action=RecommendedAction(payload.get("recommended_action", "CONTINUE")),
                confidence=float(payload.get("confidence", 0.0)),
                reasoning_summary=payload.get("reasoning_summary", ""),
                provider=self.provider_name,
            )
        except Exception as exc:  # noqa: BLE001 — must degrade gracefully, never raise into the caller
            rec = SupervisorRecommendation(
                status=HealthState.UNKNOWN,
                summary=f"Supervisor unavailable: {exc}",
                recommended_action=RecommendedAction.CONTINUE,
                confidence=0.0,
                reasoning_summary="OpenAI supervisor call failed or returned malformed output.",
                provider=self.provider_name,
            )

        rec.latency_ms = (time.perf_counter() - start) * 1000.0
        return rec
