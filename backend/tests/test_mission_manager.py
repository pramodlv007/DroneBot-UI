import pytest

from app.mission_manager import InvalidTransitionError, MissionManager, MissionStateEnum


def test_initial_state_is_disconnected():
    mgr = MissionManager()
    assert mgr.state.state == MissionStateEnum.DISCONNECTED


def test_happy_path_lifecycle():
    mgr = MissionManager()
    mgr.transition(MissionStateEnum.READY)
    mgr.transition(MissionStateEnum.ARMED)
    mgr.start(mission_id="M1", experiment_id="E1", recording=True)
    assert mgr.state.state == MissionStateEnum.RUNNING
    assert mgr.state.mission_id == "M1"

    mgr.pause()
    assert mgr.state.state == MissionStateEnum.PAUSED
    mgr.resume()
    assert mgr.state.state == MissionStateEnum.RUNNING

    mgr.stop()
    assert mgr.state.state == MissionStateEnum.STOPPED


def test_degrade_and_recover():
    mgr = MissionManager()
    mgr.transition(MissionStateEnum.READY)
    mgr.transition(MissionStateEnum.ARMED)
    mgr.start("M1", None, False)

    mgr.degrade()
    assert mgr.state.state == MissionStateEnum.DEGRADED
    mgr.recover()
    assert mgr.state.state == MissionStateEnum.RUNNING


def test_illegal_transition_raises():
    mgr = MissionManager()
    with pytest.raises(InvalidTransitionError):
        mgr.transition(MissionStateEnum.RUNNING)  # DISCONNECTED -> RUNNING is not allowed


def test_emergency_reachable_from_running_and_recoverable_via_stopped():
    mgr = MissionManager()
    mgr.transition(MissionStateEnum.READY)
    mgr.transition(MissionStateEnum.ARMED)
    mgr.start("M1", None, False)

    mgr.emergency()
    assert mgr.state.state == MissionStateEnum.EMERGENCY

    mgr.stop()
    assert mgr.state.state == MissionStateEnum.STOPPED
    mgr.ready()
    assert mgr.state.state == MissionStateEnum.READY


def test_same_state_transition_is_a_noop_not_an_error():
    mgr = MissionManager()
    result = mgr.transition(MissionStateEnum.DISCONNECTED)
    assert result.state == MissionStateEnum.DISCONNECTED
