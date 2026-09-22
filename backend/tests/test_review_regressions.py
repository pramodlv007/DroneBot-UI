"""Regression coverage for configuration, tracking, and ingest failures."""
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.adapters.turtlebot_adapter import TurtleBotAdapter
from app.main import _control_tick
from app.models import MissionStateEnum, Protocol, RobotPose, RobotState, RobotType, now_ms
from app.routers.mission_api import SetRolesRequest, StartMissionRequest
from app.state import GatewayState


def test_example_config_paths_work_from_backend(monkeypatch):
    from app.config import REPO_ROOT
    monkeypatch.chdir(REPO_ROOT / "backend")
    for variable, filename in (("ROBOTS_CONFIG_PATH", "robots.yaml"),
                               ("MISSION_CONFIG_PATH", "mission.yaml"),
                               ("SYSTEM_CONFIG_PATH", "system.yaml")):
        monkeypatch.setenv(variable, f"./config/{filename}")
    get_settings.cache_clear()
    try:
        assert "drone_01" in get_settings().robots
        assert "turtlebot_01" in get_settings().robots
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("request_model", [SetRolesRequest, StartMissionRequest])
def test_roles_require_two_distinct_robots(request_model):
    with pytest.raises(ValidationError, match="different robots"):
        request_model(leader_id="drone_01", follower_id="drone_01")


@pytest.fixture
def gateway(tmp_path):
    settings = get_settings().model_copy(deep=True)
    settings.persistence.sqlite_path = str(tmp_path / "test.db")
    settings.supervisor.provider = "disabled"
    gw = GatewayState(settings)
    yield gw
    gw.repository.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("has_sample", [False, True])
async def test_open_socket_does_not_bypass_telemetry_timeout(gateway, has_sample):
    gw = gateway
    robot = gw.registry.get("turtlebot_01")
    adapter = TurtleBotAdapter(robot.robot_id, robot.config)
    registration = await adapter.connect()
    socket = AsyncMock()
    adapter.attach_ws(socket)
    gw.registry.attach_adapter(robot.robot_id, adapter)
    gw.registry.mark_connected(robot.robot_id, registration)
    old_timestamp = now_ms() - 60_000
    robot.last_heartbeat_ms = old_timestamp
    if has_sample:
        gw.telemetry_store.update_robot_state(adapter.get_state().model_copy(
            update={"received_timestamp_ms": old_timestamp}))
    gw.coordination_manager.set_roles("drone_01", "turtlebot_01", {
        "drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV})
    gw.mission_manager.ready()
    gw.mission_manager.transition(MissionStateEnum.ARMED)
    gw.mission_manager.start("test", None, False)

    await _control_tick(gw)

    assert not robot.connected
    assert robot.robot_id not in gw.telemetry_store.robot_states
    socket.close.assert_awaited_once()
    assert gw.mission_manager.state.state == MissionStateEnum.DEGRADED


def test_ingest_uses_gateway_receive_time_and_checks_identity(gateway):
    config = gateway.registry.get("turtlebot_01").config
    adapter = TurtleBotAdapter("turtlebot_01", config)
    state = RobotState(robot_id="turtlebot_01", robot_type=RobotType.UGV,
                       protocol=Protocol.ROS2, connected=True, pose=RobotPose(),
                       source_timestamp_ms=10, received_timestamp_ms=20)
    adapter.ingest_state(state)
    assert adapter.get_state().received_timestamp_ms >= now_ms() - 1000
    assert adapter.get_state().source_timestamp_ms == 10
    assert state.received_timestamp_ms == 20
    with pytest.raises(ValueError, match="ingest slot"):
        adapter.ingest_state(state.model_copy(update={"robot_id": "drone_01"}))
    assert adapter.get_state().robot_id == "turtlebot_01"


def test_delayed_bridge_attach_gets_fresh_timeout_window(gateway, monkeypatch):
    adapter = TurtleBotAdapter("turtlebot_01", gateway.registry.get("turtlebot_01").config)
    future_ms = now_ms() + 60_000
    monkeypatch.setattr("app.adapters.turtlebot_adapter.time.time", lambda: future_ms / 1000)
    adapter.attach_ws(AsyncMock())
    assert adapter.get_state().received_timestamp_ms == future_ms
