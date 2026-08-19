import pytest

from app.coordination_manager import CoordinationManager
from app.models import (
    CoordinationMode,
    CoordinationTrackingState,
    Protocol,
    RobotPose,
    RobotState,
    RobotType,
)


def make_robot(robot_id, robot_type, x, y, yaw=0.0, connected=True) -> RobotState:
    return RobotState(
        robot_id=robot_id,
        robot_type=robot_type,
        protocol=Protocol.MOCK,
        connected=connected,
        pose=RobotPose(x=x, y=y, yaw=yaw),
    )


def test_set_roles_derives_mode_from_leader_type():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}

    mgr.set_roles("drone_01", "turtlebot_01", robot_types)
    assert mgr.mode == CoordinationMode.TURTLE_FOLLOWS_DRONE

    mgr.set_roles("turtlebot_01", "drone_01", robot_types)
    assert mgr.mode == CoordinationMode.DRONE_FOLLOWS_TURTLE


def test_role_switch_is_logged():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types, current_tracking_error_m=0.5)
    mgr.set_roles("turtlebot_01", "drone_01", robot_types, current_tracking_error_m=0.7)

    log = mgr.role_switch_log
    assert len(log) == 2
    assert log[0].previous_leader is None
    assert log[1].previous_leader == "drone_01"
    assert log[1].new_leader == "turtlebot_01"
    assert log[1].tracking_error_before_m == 0.7


def test_compute_tracking_error_and_separation():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types)

    leader = make_robot("drone_01", RobotType.UAV, x=3.0, y=0.0)
    follower = make_robot("turtlebot_01", RobotType.UGV, x=0.0, y=0.0)

    coord_state, command = mgr.compute(leader, follower)
    assert coord_state.separation_m == pytest.approx(3.0)
    assert coord_state.tracking_error_m == pytest.approx(1.5)  # |3.0 - 1.5|
    assert coord_state.state == CoordinationTrackingState.TRACKING
    assert command is not None
    assert command.robot_id == "turtlebot_01"
    assert command.linear_x > 0  # should drive toward the leader


def test_tracking_state_degrades_and_is_lost_at_thresholds():
    mgr = CoordinationManager(target_separation_m=0.0, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types)

    follower = make_robot("turtlebot_01", RobotType.UGV, x=0.0, y=0.0)

    degraded_leader = make_robot("drone_01", RobotType.UAV, x=3.0, y=0.0)
    coord_state, _ = mgr.compute(degraded_leader, follower)
    assert coord_state.state == CoordinationTrackingState.DEGRADED

    lost_leader = make_robot("drone_01", RobotType.UAV, x=5.0, y=0.0)
    coord_state, command = mgr.compute(lost_leader, follower)
    assert coord_state.state == CoordinationTrackingState.LOST
    assert command is None  # no command issued once tracking is LOST


def test_disconnected_robot_forces_lost_state():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types)

    leader = make_robot("drone_01", RobotType.UAV, x=1.5, y=0.0, connected=False)
    follower = make_robot("turtlebot_01", RobotType.UGV, x=0.0, y=0.0)

    coord_state, command = mgr.compute(leader, follower)
    assert coord_state.state == CoordinationTrackingState.LOST
    assert command is None


def test_stop_distance_zeroes_command():
    mgr = CoordinationManager(target_separation_m=0.25, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types)

    leader = make_robot("drone_01", RobotType.UAV, x=0.1, y=0.0)
    follower = make_robot("turtlebot_01", RobotType.UGV, x=0.0, y=0.0)

    _, command = mgr.compute(leader, follower)
    assert command.linear_x == 0.0
    assert command.angular_z == 0.0
