"""
Deterministic validator for LLM-produced recommendations (§22, §48). The
LLM must never be trusted to emit a safe/well-formed recommendation on its
own — this validator is the boundary between "text an LLM produced" and
"something the rest of the system is allowed to display or act on
awareness-wise." It NEVER turns a recommendation into an actuator command;
it only decides whether the recommendation itself is well-formed enough to
surface to the operator, downgrading to a safe default otherwise.
"""

from __future__ import annotations

from app.models import HealthState, RecommendedAction, SupervisorRecommendation

_ALLOWED_ACTIONS = set(RecommendedAction)
_FORBIDDEN_KEYWORDS = (
    "linear_x", "linear_y", "angular_z", "pwm", "throttle", "motor",
    "set_position_target", "cmd_vel", "arm(", "takeoff(",
)


def validate_recommendation(raw: SupervisorRecommendation) -> SupervisorRecommendation:
    """Returns a safe recommendation: either `raw` unchanged if it passes
    validation, or a conservative fallback (RETURN_TO_SAFE_STATE / WARNING)
    if the LLM output looks malformed or attempts to smuggle actuator
    values through free-text fields."""

    if raw.recommended_action not in _ALLOWED_ACTIONS:
        return _fallback(f"Unrecognized recommended_action: {raw.recommended_action!r}")

    if not (0.0 <= raw.confidence <= 1.0):
        return _fallback("Confidence out of range")

    text_fields = f"{raw.summary} {raw.detected_issue or ''} {raw.reasoning_summary}".lower()
    for keyword in _FORBIDDEN_KEYWORDS:
        if keyword in text_fields:
            return _fallback(f"Recommendation text referenced actuator-level term '{keyword}'")

    return raw


def _fallback(reason: str) -> SupervisorRecommendation:
    return SupervisorRecommendation(
        status=HealthState.WARNING,
        summary=f"Supervisor output rejected by validator: {reason}",
        detected_issue="INVALID_SUPERVISOR_OUTPUT",
        recommended_action=RecommendedAction.RETURN_TO_SAFE_STATE,
        confidence=0.0,
        reasoning_summary="Deterministic validator replaced an unsafe or malformed LLM recommendation.",
        provider="validator",
    )
