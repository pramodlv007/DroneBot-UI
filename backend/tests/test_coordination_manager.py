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


def test_attitude_follow_pitch_forward():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types, mode=CoordinationMode.ATTITUDE_FOLLOW)

    # Drone nose down (pitch = -0.2 rad ~ -11.5 deg), level roll, aligned yaw
    leader = RobotState(
        robot_id="drone_01",
        robot_type=RobotType.UAV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=1.5, roll=0.0, pitch=-0.2, yaw=0.0),
    )
    follower = RobotState(
        robot_id="turtlebot_01",
        robot_type=RobotType.UGV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
    )

    coord_state, command = mgr.compute(leader, follower)
    assert coord_state.mode == CoordinationMode.ATTITUDE_FOLLOW
    assert coord_state.state == CoordinationTrackingState.TRACKING
    assert command is not None
    assert command.linear_x > 0.0  # Should drive forward
    assert command.angular_z == 0.0
    assert coord_state.motion_intent == "DRIVING FORWARD"


def test_attitude_follow_pitch_backward():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types, mode=CoordinationMode.ATTITUDE_FOLLOW)

    # Drone nose up (pitch = +0.2 rad), level roll, aligned yaw
    leader = RobotState(
        robot_id="drone_01",
        robot_type=RobotType.UAV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=1.5, roll=0.0, pitch=0.2, yaw=0.0),
    )
    follower = RobotState(
        robot_id="turtlebot_01",
        robot_type=RobotType.UGV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
    )

    coord_state, command = mgr.compute(leader, follower)
    assert command is not None
    assert command.linear_x < 0.0  # Should reverse
    assert coord_state.motion_intent == "REVERSING"


def test_attitude_follow_deadband_zeroes():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types, mode=CoordinationMode.ATTITUDE_FOLLOW)

    # Drone tilted only 0.02 rad (~1.1 deg, well within 0.05 rad deadband)
    leader = RobotState(
        robot_id="drone_01",
        robot_type=RobotType.UAV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=1.5, roll=0.02, pitch=-0.02, yaw=0.01),
    )
    follower = RobotState(
        robot_id="turtlebot_01",
        robot_type=RobotType.UGV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
    )

    coord_state, command = mgr.compute(leader, follower)
    assert command is not None
    assert command.linear_x == 0.0
    assert command.angular_z == 0.0
    assert coord_state.motion_intent == "LEVEL / STATIONARY"


def test_attitude_follow_yaw_alignment():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types, mode=CoordinationMode.ATTITUDE_FOLLOW)

    # Drone yaw = +0.5 rad (CCW), TurtleBot yaw = 0.0 rad -> should rotate CCW (angular_z > 0)
    leader = RobotState(
        robot_id="drone_01",
        robot_type=RobotType.UAV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=1.5, roll=0.0, pitch=0.0, yaw=0.5),
    )
    follower = RobotState(
        robot_id="turtlebot_01",
        robot_type=RobotType.UGV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
    )

    coord_state, command = mgr.compute(leader, follower)
    assert command is not None
    assert command.angular_z > 0.0  # Turn left/CCW to align
    assert coord_state.motion_intent == "ROTATING LEFT"


def test_attitude_follow_roll_banking():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types, mode=CoordinationMode.ATTITUDE_FOLLOW)

    # Drone roll = +0.3 rad (tilt right) -> should turn right (angular_z < 0)
    leader = RobotState(
        robot_id="drone_01",
        robot_type=RobotType.UAV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=1.5, roll=0.3, pitch=0.0, yaw=0.0),
    )
    follower = RobotState(
        robot_id="turtlebot_01",
        robot_type=RobotType.UGV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
    )

    coord_state, command = mgr.compute(leader, follower)
    assert command is not None
    assert command.angular_z < 0.0  # Turn right
    assert coord_state.motion_intent == "ROTATING RIGHT"


def test_attitude_follow_clamping():
    mgr = CoordinationManager(target_separation_m=1.5, tracking_error_degraded_m=2.0, tracking_error_lost_m=4.0)
    mgr.configure_limits(max_linear_speed_mps=0.22, max_angular_speed_radps=1.0)
    robot_types = {"drone_01": RobotType.UAV, "turtlebot_01": RobotType.UGV}
    mgr.set_roles("drone_01", "turtlebot_01", robot_types, mode=CoordinationMode.ATTITUDE_FOLLOW)

    # Extreme tilt (pitch = -1.2 rad, roll = 1.0 rad, yaw = 2.0 rad)
    leader = RobotState(
        robot_id="drone_01",
        robot_type=RobotType.UAV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=1.5, roll=1.0, pitch=-1.2, yaw=2.0),
    )
    follower = RobotState(
        robot_id="turtlebot_01",
        robot_type=RobotType.UGV,
        protocol=Protocol.MOCK,
        connected=True,
        pose=RobotPose(x=0.0, y=0.0, z=0.0, roll=0.0, pitch=0.0, yaw=0.0),
    )

    _, command = mgr.compute(leader, follower)
    assert command is not None
    assert abs(command.linear_x) <= 0.22
    assert abs(command.angular_z) <= 1.0

