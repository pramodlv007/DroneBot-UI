import tempfile
from pathlib import Path

import pytest

from app.db import SQLiteExperimentRepository
from app.experiment_recorder import ExperimentRecorder
from app.models import (
    CoordinationMode,
    CoordinationState,
    CoordinationTrackingState,
    EventSeverity,
    HealthState,
    MissionEvent,
    RecommendedAction,
    SupervisorRecommendation,
)


@pytest.fixture
def recorder():
    with tempfile.TemporaryDirectory() as tmp:
        repo = SQLiteExperimentRepository(str(Path(tmp) / "test.db"))
        yield ExperimentRecorder(repo)
        repo.close()  # release the OS file handle before the tempdir is removed (required on Windows)


def test_metrics_computed_from_coordination_samples(recorder):
    recorder.start(
        "EXP_1", "test", "M1", "drone_01", "turtlebot_01", llm_enabled=True, llm_provider="mock", config={}
    )

    for tracking_error in (1.0, 2.0, 3.0, 4.0):
        recorder.record_coordination(
            CoordinationState(
                leader_id="drone_01",
                follower_id="turtlebot_01",
                mode=CoordinationMode.TURTLE_FOLLOWS_DRONE,
                separation_m=1.5 + tracking_error,
                tracking_error_m=tracking_error,
                telemetry_latency_ms=10.0,
                state=CoordinationTrackingState.TRACKING,
            )
        )

    recorder.record_recommendation(
        SupervisorRecommendation(
            status=HealthState.NORMAL,
            summary="ok",
            recommended_action=RecommendedAction.CONTINUE,
            confidence=0.9,
            latency_ms=50.0,
            provider="mock",
        )
    )
    recorder.record_event(MissionEvent(type="TEST_WARNING", severity=EventSeverity.WARNING))
    recorder.record_event(MissionEvent(type="TEST_CRITICAL", severity=EventSeverity.CRITICAL))

    recorder.stop()

    metrics = recorder.compute_metrics("EXP_1")
    assert metrics.mean_tracking_error_m == pytest.approx(2.5)
    assert metrics.max_tracking_error_m == pytest.approx(4.0)
    assert metrics.tracking_rmse_m == pytest.approx((sum(v * v for v in (1, 2, 3, 4)) / 4) ** 0.5)
    assert metrics.warning_count == 1
    assert metrics.critical_event_count == 1
    assert metrics.llm_recommendation_count == 1
    assert metrics.mean_llm_latency_ms == pytest.approx(50.0)
    assert metrics.mission_duration_s is not None


def test_export_json_contains_all_streams(recorder):
    recorder.start("EXP_2", "test", "M2", "drone_01", "turtlebot_01", llm_enabled=False, llm_provider="disabled", config={})
    recorder.record_coordination(
        CoordinationState(mode=CoordinationMode.IDLE, state=CoordinationTrackingState.IDLE)
    )
    recorder.stop()

    export = recorder.export_json("EXP_2")
    assert export["experiment"]["id"] == "EXP_2"
    assert len(export["coordination"]) == 1
    assert "metrics" in export


def test_export_csv_has_header_and_row(recorder):
    recorder.start("EXP_3", "test", "M3", "drone_01", "turtlebot_01", llm_enabled=False, llm_provider="disabled", config={})
    recorder.record_coordination(
        CoordinationState(mode=CoordinationMode.IDLE, tracking_error_m=1.2, state=CoordinationTrackingState.TRACKING)
    )
    recorder.stop()

    csv_text = recorder.export_csv("EXP_3")
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("timestamp_ms")
    assert len(lines) == 2
