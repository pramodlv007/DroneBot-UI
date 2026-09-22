import time

import pytest

from app.config import SafetyConfig
from app.models import MissionStateEnum, Protocol, RobotCommand, RobotPose, RobotState, RobotType, now_ms
from app.safety_manager import SafetyManager


def make_state(connected=True, age_s=0.0) -> RobotState:
    ts = now_ms() - int(age_s * 1000)
    return RobotState(
        robot_id="turtlebot_01",
        robot_type=RobotType.UGV,
        protocol=Protocol.MOCK,
        connected=connected,
        pose=RobotPose(),
        source_timestamp_ms=ts,
        received_timestamp_ms=ts,
    )


def make_manager(**overrides) -> SafetyManager:
    config = SafetyConfig(**{"telemetry_stale_s": 2.0, "max_command_rate_hz": 20, **overrides})
    return SafetyManager(config, max_linear_speed_mps=0.22, max_angular_speed_radps=1.0)


def test_blocks_when_emergency_active():
    mgr = make_manager()
    mgr.trigger_emergency_stop("test", {})
    cmd = RobotCommand(robot_id="turtlebot_01", linear_x=0.1)
    result = mgr.check_and_clamp(cmd, make_state(), MissionStateEnum.RUNNING)
    assert not result.allowed
    assert result.reason == "EMERGENCY_STOP_ACTIVE"


def test_blocks_when_mission_not_running():
    mgr = make_manager()
    cmd = RobotCommand(robot_id="turtlebot_01", linear_x=0.1)
    result = mgr.check_and_clamp(cmd, make_state(), MissionStateEnum.PAUSED)
    assert not result.allowed
    assert "MISSION_STATE" in result.reason


def test_blocks_when_robot_not_connected():
    mgr = make_manager()
    cmd = RobotCommand(robot_id="turtlebot_01", linear_x=0.1)
    result = mgr.check_and_clamp(cmd, make_state(connected=False), MissionStateEnum.RUNNING)
    assert not result.allowed
    assert result.reason == "ROBOT_NOT_CONNECTED"


def test_blocks_when_telemetry_stale():
    mgr = make_manager(telemetry_stale_s=1.0)
    cmd = RobotCommand(robot_id="turtlebot_01", linear_x=0.1)
    result = mgr.check_and_clamp(cmd, make_state(age_s=5.0), MissionStateEnum.RUNNING)
    assert not result.allowed
    assert result.reason == "TELEMETRY_STALE"


def test_clamps_excessive_velocity():
    mgr = make_manager()
    cmd = RobotCommand(robot_id="turtlebot_01", linear_x=999.0, angular_z=-999.0)
    result = mgr.check_and_clamp(cmd, make_state(), MissionStateEnum.RUNNING)
    assert result.allowed
    assert result.command.linear_x == pytest.approx(0.22)
    assert result.command.angular_z == pytest.approx(-1.0)


def test_command_rate_limit():
    mgr = make_manager(max_command_rate_hz=1)  # 1000ms min interval
    cmd = RobotCommand(robot_id="turtlebot_01", linear_x=0.1)
    first = mgr.check_and_clamp(cmd, make_state(), MissionStateEnum.RUNNING)
    assert first.allowed
    second = mgr.check_and_clamp(cmd, make_state(), MissionStateEnum.RUNNING)
    assert not second.allowed
    assert second.reason == "COMMAND_RATE_LIMITED"


def test_emergency_clear_restores_normal_operation():
    mgr = make_manager()
    mgr.trigger_emergency_stop("test", {})
    assert mgr.emergency
    mgr.clear_emergency_stop()
    assert not mgr.emergency
    cmd = RobotCommand(robot_id="turtlebot_01", linear_x=0.1)
    result = mgr.check_and_clamp(cmd, make_state(), MissionStateEnum.RUNNING)
    assert result.allowed


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", ["linear_x", "linear_y", "angular_z"])
def test_rejects_nonfinite_commands(value, field):
    result = make_manager().check_and_clamp(
        RobotCommand(robot_id="turtlebot_01", **{field: value}), make_state(), MissionStateEnum.RUNNING)
    assert not result.allowed
    assert result.reason == "NON_FINITE_COMMAND"


def test_clamps_vector_speed_preserving_direction():
    import math
    result = make_manager().check_and_clamp(
        RobotCommand(robot_id="turtlebot_01", linear_x=3, linear_y=-4), make_state(), MissionStateEnum.RUNNING)
    assert result.allowed
    assert math.hypot(result.command.linear_x, result.command.linear_y) == pytest.approx(0.22)
    assert result.command.linear_x / result.command.linear_y == pytest.approx(-0.75)


def test_rejects_wrong_robot_state():
    result = make_manager().check_and_clamp(
        RobotCommand(robot_id="drone_01"), make_state(), MissionStateEnum.RUNNING)
    assert not result.allowed
    assert result.reason == "ROBOT_ID_MISMATCH"
