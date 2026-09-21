from app.anomaly_detector import AnomalyDetector
from app.config import AnomalyConfig
from app.models import (
    BatteryState,
    Protocol,
    RobotCommand,
    RobotPose,
    RobotState,
    RobotType,
)

ROBOT_ID = "turtlebot_01"


def make_state(x=0.0, y=0.0, yaw=0.0, battery_pct=None, connected=True) -> RobotState:
    return RobotState(
        robot_id=ROBOT_ID,
        robot_type=RobotType.UGV,
        protocol=Protocol.MOCK,
        connected=connected,
        pose=RobotPose(x=x, y=y, yaw=yaw),
        battery=BatteryState(percentage=battery_pct) if battery_pct is not None else None,
    )


def make_detector(**overrides) -> AnomalyDetector:
    return AnomalyDetector(AnomalyConfig(**overrides))


def tick(detector, ts_ms, state, command=None, mission_running=True):
    return detector.evaluate(ts_ms, {ROBOT_ID: state}, command, mission_running)


def test_no_anomalies_on_healthy_telemetry():
    det = make_detector()
    events = []
    for i in range(50):
        events += tick(det, i * 100, make_state(x=i * 0.001))
    assert events == []


def test_stuck_fires_when_commanded_but_not_moving():
    det = make_detector(stuck_window_s=1.0, stuck_distance_m=0.05)
    cmd = RobotCommand(robot_id=ROBOT_ID, linear_x=0.2)
    events = []
    # 1.5s of ticks at 100ms, robot commanded to move but position frozen
    for i in range(15):
        events += tick(det, i * 100, make_state(x=0.0), command=cmd)
    types = [e.type for e in events]
    assert "ANOMALY_STUCK" in types


def test_stuck_does_not_fire_when_robot_is_actually_moving():
    det = make_detector(stuck_window_s=1.0, stuck_distance_m=0.05)
    cmd = RobotCommand(robot_id=ROBOT_ID, linear_x=0.2)
    events = []
    for i in range(15):
        events += tick(det, i * 100, make_state(x=i * 0.02), command=cmd)  # moving ~0.2m/s
    assert all(e.type != "ANOMALY_STUCK" for e in events)


def test_stuck_does_not_fire_without_a_command():
    det = make_detector(stuck_window_s=1.0, stuck_distance_m=0.05)
    events = []
    for i in range(15):
        events += tick(det, i * 100, make_state(x=0.0), command=None)
    assert all(e.type != "ANOMALY_STUCK" for e in events)


def test_stuck_ignores_a_command_for_a_different_robot():
    det = make_detector(stuck_window_s=1.0, stuck_distance_m=0.05)
    cmd = RobotCommand(robot_id="drone_01", linear_x=0.2)
    events = []
    for i in range(15):
        events += tick(det, i * 100, make_state(x=0.0), command=cmd)
    assert all(e.type != "ANOMALY_STUCK" for e in events)


def test_stuck_recovers_once_robot_starts_moving():
    det = make_detector(stuck_window_s=1.0, stuck_distance_m=0.05, cooldown_s=0.0)
    cmd = RobotCommand(robot_id=ROBOT_ID, linear_x=0.2)
    events = []
    for i in range(15):
        events += tick(det, i * 100, make_state(x=0.0), command=cmd)
    assert any(e.type == "ANOMALY_STUCK" for e in events)

    recovery_events = []
    for i in range(15, 30):
        recovery_events += tick(det, i * 100, make_state(x=(i - 14) * 0.05), command=cmd)
    assert any(e.type == "ANOMALY_STUCK_RECOVERED" for e in recovery_events)


def test_position_jump_detected():
    det = make_detector(position_jump_max_speed_mps=5.0)
    events = tick(det, 0, make_state(x=0.0, y=0.0))
    events += tick(det, 100, make_state(x=10.0, y=0.0))  # 10m in 100ms = 100 m/s
    assert any(e.type == "ANOMALY_POSITION_JUMP" for e in events)


def test_position_jump_not_flagged_for_plausible_motion():
    det = make_detector(position_jump_max_speed_mps=5.0)
    events = tick(det, 0, make_state(x=0.0, y=0.0))
    events += tick(det, 1000, make_state(x=1.0, y=0.0))  # 1 m/s, well under threshold
    assert all(e.type != "ANOMALY_POSITION_JUMP" for e in events)


def test_battery_drain_detected():
    det = make_detector(battery_window_s=1.0, battery_drop_pct=5.0)
    events = []
    # 1s+ of samples, battery falling fast (10% over the window)
    for i in range(13):
        events += tick(det, i * 100, make_state(battery_pct=100.0 - i))
    assert any(e.type == "ANOMALY_BATTERY_DRAIN" for e in events)


def test_battery_drain_not_flagged_for_normal_discharge():
    det = make_detector(battery_window_s=1.0, battery_drop_pct=5.0)
    events = []
    for i in range(13):
        events += tick(det, i * 100, make_state(battery_pct=100.0 - i * 0.01))
    assert all(e.type != "ANOMALY_BATTERY_DRAIN" for e in events)


def test_heading_oscillation_detected():
    det = make_detector(heading_oscillation_window_s=1.0, heading_oscillation_min_flips=3)
    events = []
    yaws = [0.5, -0.5, 0.5, -0.5, 0.5, -0.5, 0.5, -0.5]
    for i, yaw in enumerate(yaws):
        events += tick(det, i * 100, make_state(yaw=yaw))
    assert any(e.type == "ANOMALY_HEADING_OSCILLATION" for e in events)


def test_heading_oscillation_not_flagged_for_smooth_turn():
    det = make_detector(heading_oscillation_window_s=1.0, heading_oscillation_min_flips=3)
    events = []
    for i in range(10):
        events += tick(det, i * 100, make_state(yaw=i * 0.1))  # monotonic turn
    assert all(e.type != "ANOMALY_HEADING_OSCILLATION" for e in events)


def test_disconnect_clears_history_so_reconnect_does_not_false_positive():
    det = make_detector(stuck_window_s=1.0, stuck_distance_m=0.05)
    cmd = RobotCommand(robot_id=ROBOT_ID, linear_x=0.2)
    for i in range(15):
        tick(det, i * 100, make_state(x=0.0), command=cmd)
    assert ROBOT_ID in det._tracks

    tick(det, 1600, make_state(connected=False))
    assert ROBOT_ID not in det._tracks

    # Reconnect at a far-away position with a fresh command — must not
    # immediately compare against pre-disconnect history.
    events = tick(det, 1700, make_state(x=50.0), command=cmd)
    assert all(e.type != "ANOMALY_STUCK" for e in events)


def test_disabled_config_produces_no_events():
    det = make_detector(enabled=False)
    cmd = RobotCommand(robot_id=ROBOT_ID, linear_x=0.2)
    events = []
    for i in range(20):
        events += tick(det, i * 100, make_state(x=0.0, battery_pct=100.0 - i), command=cmd)
    assert events == []
