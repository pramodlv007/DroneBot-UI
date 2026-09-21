from app.routers.ai_monitor_api import MonitorRequest, _rule_based_monitor


def make_robot(robot_type="UGV", battery_pct=80.0, dead_reckoning=False, gps_fix=None, mode=None):
    rs = {
        "robot_type": robot_type,
        "battery": {"percentage": battery_pct},
        "source_timestamp_ms": 1000,
        "received_timestamp_ms": 1050,
        "velocity": {"linear_x": 0.2, "linear_y": 0.0, "linear_z": 0.0},
        "metadata": {"dead_reckoning_active": dead_reckoning},
    }
    if gps_fix is not None:
        rs["gps"] = {"fix": gps_fix, "altitude": 5.0}
    if mode is not None:
        rs["mode"] = mode
    return rs


def test_nominal_when_nothing_wrong():
    req = MonitorRequest(robots={"turtlebot_01": make_robot()}, coordination={}, mission={"state": "RUNNING"})
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "NOMINAL"
    assert resp.recommended_action == "CONTINUE"


def test_emergency_state_overrides_everything():
    req = MonitorRequest(
        robots={"turtlebot_01": make_robot(battery_pct=90.0)},
        coordination={},
        mission={"state": "EMERGENCY"},
    )
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "CRITICAL"
    assert resp.recommended_action == "STOP"
    assert any("EMERGENCY" in a for a in resp.alerts)


def test_active_anomaly_from_detector_is_surfaced_and_recommends_pause():
    req = MonitorRequest(
        robots={"turtlebot_01": make_robot()},
        coordination={},
        mission={"state": "RUNNING"},
        anomalies={"turtlebot_01": ["STUCK"]},
    )
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "WARNING"
    assert resp.recommended_action == "PAUSE"
    assert any("turtlebot_01" in a for a in resp.alerts)


def test_detector_stuck_anomaly_suppresses_duplicate_velocity_heuristic():
    # Robot reports near-zero velocity AND the detector already flagged STUCK
    # — the fallback heuristic must not also fire a second, redundant alert.
    robot = make_robot()
    robot["velocity"] = {"linear_x": 0.0, "linear_y": 0.0, "linear_z": 0.0}
    req = MonitorRequest(
        robots={"turtlebot_01": robot},
        coordination={},
        mission={"state": "RUNNING"},
        anomalies={"turtlebot_01": ["STUCK"]},
    )
    resp = _rule_based_monitor(req)
    stall_alerts = [a for a in resp.alerts if "possible stall" in a]
    assert stall_alerts == []


def test_velocity_heuristic_fires_when_no_detector_anomaly_present():
    robot = make_robot()
    robot["velocity"] = {"linear_x": 0.0, "linear_y": 0.0, "linear_z": 0.0}
    req = MonitorRequest(robots={"turtlebot_01": robot}, coordination={}, mission={"state": "RUNNING"})
    resp = _rule_based_monitor(req)
    assert any("possible stall" in a for a in resp.alerts)
    assert resp.overall_status == "WARNING"


def test_dead_reckoning_flagged_as_warning():
    req = MonitorRequest(
        robots={"drone_01": make_robot(robot_type="UAV", dead_reckoning=True)},
        coordination={},
        mission={"state": "RUNNING"},
    )
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "WARNING"
    assert any("ESTIMATE" in a for a in resp.alerts)


def test_battery_critical_recommends_return_to_safe_state():
    req = MonitorRequest(
        robots={"turtlebot_01": make_robot(battery_pct=10.0)},
        coordination={},
        mission={"state": "RUNNING"},
    )
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "CRITICAL"
    assert resp.recommended_action == "RETURN_TO_SAFE_STATE"


def test_weak_gps_recommends_check_gps():
    req = MonitorRequest(
        robots={"drone_01": make_robot(robot_type="UAV", gps_fix=1)},
        coordination={},
        mission={"state": "RUNNING"},
    )
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "WARNING"
    assert resp.recommended_action == "CHECK_GPS"


def test_high_telemetry_lag_recommends_check_communication():
    robot = make_robot()
    robot["source_timestamp_ms"] = 1000
    robot["received_timestamp_ms"] = 1600  # 600ms lag
    req = MonitorRequest(robots={"turtlebot_01": robot}, coordination={}, mission={"state": "RUNNING"})
    resp = _rule_based_monitor(req)
    assert resp.recommended_action == "CHECK_COMMUNICATION"


def test_diverging_prediction_flagged_before_threshold_crossed():
    req = MonitorRequest(
        robots={},
        coordination={
            "leader_id": "drone_01",
            "follower_id": "turtlebot_01",
            "separation_m": 1.6,
            "target_separation_m": 1.5,
            "predicted_separation_m": 4.0,
            "predicted_tracking_error_m": 2.5,
            "separation_trend": "DIVERGING",
        },
        mission={"state": "RUNNING"},
    )
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "WARNING"
    assert resp.recommended_action == "SLOW_DOWN"
    assert any("diverging" in a.lower() for a in resp.alerts)


def test_mission_health_score_names_weakest_component():
    req = MonitorRequest(
        robots={},
        coordination={
            "leader_id": "drone_01",
            "follower_id": "turtlebot_01",
            "mission_health_score": 45.0,
            "mission_health_components": {"tracking": 90.0, "latency": 95.0, "battery": 20.0, "gps": 80.0, "safety": 100.0},
        },
        mission={"state": "RUNNING"},
    )
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "WARNING"
    assert any("battery" in u for u in resp.updates)


def test_action_priority_keeps_the_most_severe_recommendation():
    # Both a CHECK_GPS-level issue and a STOP-level emergency are present —
    # the higher-priority action must win, not whichever check ran last.
    req = MonitorRequest(
        robots={"drone_01": make_robot(robot_type="UAV", gps_fix=1)},
        coordination={},
        mission={"state": "EMERGENCY"},
    )
    resp = _rule_based_monitor(req)
    assert resp.recommended_action == "STOP"


def test_no_data_still_returns_a_valid_response():
    req = MonitorRequest(robots={}, coordination={}, mission={})
    resp = _rule_based_monitor(req)
    assert resp.overall_status == "NOMINAL"
    assert resp.recommended_action == "CONTINUE"
    assert resp.updates


def test_disconnected_with_no_robots_gives_a_standing_by_message_not_zeros():
    # This is the exact scenario that used to produce "Mission state:
    # DISCONNECTED / Separation: 0.00 m (target 1.5 m) / Mission health:
    # 72/100" — meaningless numbers from a coordination pair that doesn't
    # exist. It must not mention separation/tracking/health at all.
    req = MonitorRequest(
        robots={},
        coordination={"separation_m": 0.0, "target_separation_m": 1.5, "mission_health_score": 72.0},
        mission={"state": "DISCONNECTED"},
    )
    resp = _rule_based_monitor(req)
    joined = " ".join(resp.updates + resp.alerts).lower()
    assert "separation" not in joined
    assert "mission health" not in joined
    assert "connect" in joined
    assert resp.provider == "rule_based"


def test_connected_but_no_coordination_pair_still_avoids_fake_separation():
    req = MonitorRequest(
        robots={"turtlebot_01": make_robot()},
        coordination={"separation_m": 0.0, "target_separation_m": 1.5},
        mission={"state": "READY"},
    )
    resp = _rule_based_monitor(req)
    joined = " ".join(resp.updates + resp.alerts).lower()
    assert "separation" not in joined
    assert "leader" in joined or "follower" in joined


def test_active_coordination_pair_reports_real_separation():
    req = MonitorRequest(
        robots={},
        coordination={"leader_id": "drone_01", "follower_id": "turtlebot_01", "separation_m": 1.4, "target_separation_m": 1.5},
        mission={"state": "RUNNING"},
    )
    resp = _rule_based_monitor(req)
    assert any("separation" in u.lower() for u in resp.updates)
    assert resp.overall_status == "NOMINAL"
