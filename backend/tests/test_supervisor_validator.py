from app.models import HealthState, RecommendedAction, SupervisorRecommendation
from app.supervisor.validator import validate_recommendation


def make_rec(**overrides) -> SupervisorRecommendation:
    defaults = dict(
        status=HealthState.NORMAL,
        summary="All nominal.",
        recommended_action=RecommendedAction.CONTINUE,
        confidence=0.9,
        reasoning_summary="Nothing unusual.",
        provider="mock",
    )
    defaults.update(overrides)
    return SupervisorRecommendation(**defaults)


def test_valid_recommendation_passes_through_unchanged():
    rec = make_rec()
    result = validate_recommendation(rec)
    assert result is rec


def test_out_of_range_confidence_is_replaced():
    # model_construct bypasses pydantic validation, simulating a malformed
    # upstream LLM payload that the validator must still catch.
    rec = SupervisorRecommendation.model_construct(
        status=HealthState.NORMAL,
        summary="All nominal.",
        recommended_action=RecommendedAction.CONTINUE,
        confidence=5.0,
        reasoning_summary="",
        provider="mock",
    )
    result = validate_recommendation(rec)
    assert result.recommended_action == RecommendedAction.RETURN_TO_SAFE_STATE
    assert result.provider == "validator"


def test_actuator_level_language_is_rejected():
    rec = make_rec(reasoning_summary="Set linear_x to 0.3 and angular_z to -0.2 immediately.")
    result = validate_recommendation(rec)
    assert result.recommended_action == RecommendedAction.RETURN_TO_SAFE_STATE
    assert result.confidence == 0.0
    assert result.provider == "validator"


def test_pwm_keyword_in_summary_is_rejected():
    rec = make_rec(summary="Recommend setting PWM to 1500 on channel 3.")
    result = validate_recommendation(rec)
    assert result.provider == "validator"


def test_valid_action_values_all_pass():
    for action in RecommendedAction:
        rec = make_rec(recommended_action=action)
        result = validate_recommendation(rec)
        assert result.recommended_action == action
