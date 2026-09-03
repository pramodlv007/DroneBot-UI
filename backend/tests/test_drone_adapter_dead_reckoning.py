"""
Exercises DroneAdapter's indoor/GPS-denied dead-reckoning fallback directly
against fabricated MAVLink messages — no real pymavlink connection needed,
since DroneAdapter.__init__/._handle_message never touch the network.
"""

import math

import pytest

import app.adapters.drone_adapter as drone_adapter_module
from app.adapters.drone_adapter import DroneAdapter
from app.config import RobotConfig


class FakeMsg:
    def __init__(self, type_name, **fields):
        self._type = type_name
        for k, v in fields.items():
            setattr(self, k, v)

    def get_type(self):
        return self._type


class FakeClock:
    """Lets a test advance app.adapters.drone_adapter's now_ms() deterministically."""

    def __init__(self, start_ms: int = 0) -> None:
        self.ms = start_ms

    def __call__(self) -> int:
        return self.ms

    def advance(self, delta_ms: int) -> None:
        self.ms += delta_ms


def make_adapter(monkeypatch) -> tuple[DroneAdapter, FakeClock]:
    config = RobotConfig(type="UAV", protocol="MAVLink", display_name="Test UAV", connection="udp:0.0.0.0:14550")
    adapter = DroneAdapter("drone_01", config)
    clock = FakeClock(1_000_000)
    monkeypatch.setattr(drone_adapter_module, "now_ms", clock)
    return adapter, clock


def test_dead_reckoning_off_by_default_leaves_position_at_origin(monkeypatch):
    adapter, clock = make_adapter(monkeypatch)
    adapter._handle_message(FakeMsg("ATTITUDE", roll=0.0, pitch=0.0, yaw=math.pi / 2))  # NED 90deg (East) -> ENU yaw=0
    clock.advance(100)
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=3.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))
    state = adapter.get_state()
    assert state.pose.x == 0.0 and state.pose.y == 0.0
    assert state.metadata.get("dead_reckoning_active") is not True


def test_dead_reckoning_engages_when_enabled_and_no_gps_fix(monkeypatch):
    adapter, clock = make_adapter(monkeypatch)
    adapter.set_dead_reckoning(True)
    assert adapter.dead_reckoning_enabled

    adapter._handle_message(FakeMsg("ATTITUDE", roll=0.0, pitch=0.0, yaw=math.pi / 2))  # NED 90deg (East) -> ENU yaw=0
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=2.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))  # baseline tick

    clock.advance(1000)
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=2.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))

    state = adapter.get_state()
    assert state.metadata["dead_reckoning_active"] is True
    assert state.gps is None
    assert state.pose.x == pytest.approx(2.0)
    assert adapter.dead_reckoning_active


def test_real_position_source_wins_over_dead_reckoning(monkeypatch):
    adapter, clock = make_adapter(monkeypatch)
    adapter.set_dead_reckoning(True)

    adapter._handle_message(FakeMsg("ATTITUDE", roll=0.0, pitch=0.0, yaw=math.pi / 2))  # NED 90deg (East) -> ENU yaw=0
    # A real LOCAL_POSITION_NED fix just arrived (e.g. optical flow) —
    # dead reckoning must not fight it even though there's no GPS fix.
    adapter._handle_message(FakeMsg("LOCAL_POSITION_NED", x=1.0, y=2.0, z=-3.0))

    clock.advance(50)  # well within the 500ms "recent real position" window
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=10.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))

    state = adapter.get_state()
    assert state.metadata.get("dead_reckoning_active") is not True
    assert not adapter.dead_reckoning_active


def test_gps_reacquired_stops_dead_reckoning_and_resumes_gps_position(monkeypatch):
    adapter, clock = make_adapter(monkeypatch)
    adapter.set_dead_reckoning(True)
    adapter._handle_message(FakeMsg("ATTITUDE", roll=0.0, pitch=0.0, yaw=math.pi / 2))  # NED 90deg (East) -> ENU yaw=0

    # No fix -> dead reckoning engages
    adapter._handle_message(FakeMsg("GPS_RAW_INT", fix_type=0))
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=1.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))
    clock.advance(500)
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=1.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))
    assert adapter.dead_reckoning_active

    # Fix reacquired -> real GPS position must take back over
    adapter._handle_message(FakeMsg("GPS_RAW_INT", fix_type=3))
    adapter._handle_message(
        FakeMsg("GLOBAL_POSITION_INT", lat=374275000, lon=-1221697000, relative_alt=5000, alt=5000)
    )

    state = adapter.get_state()
    assert state.gps is not None
    assert state.metadata["dead_reckoning_active"] is False
    assert not adapter.dead_reckoning_active


def test_gps_loss_seeds_dead_reckoning_from_last_known_position(monkeypatch):
    adapter, clock = make_adapter(monkeypatch)
    adapter.set_dead_reckoning(True)
    adapter._handle_message(FakeMsg("ATTITUDE", roll=0.0, pitch=0.0, yaw=math.pi / 2))  # NED 90deg (East) -> ENU yaw=0

    # Good GPS fix and a real published position far from the origin.
    adapter._handle_message(FakeMsg("GPS_RAW_INT", fix_type=3))
    adapter._handle_message(
        FakeMsg("GLOBAL_POSITION_INT", lat=374275000, lon=-1221697000, relative_alt=5000, alt=5000)
    )
    seeded_x = adapter.get_state().pose.x
    seeded_y = adapter.get_state().pose.y

    # GPS drops indoors — dead reckoning must continue from that last known
    # position, not jump back to (0, 0).
    adapter._handle_message(FakeMsg("GPS_RAW_INT", fix_type=0))
    clock.advance(600)  # let the "recent real position" grace window elapse
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=1.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))  # baseline
    clock.advance(1000)
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=1.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))

    state = adapter.get_state()
    assert state.metadata["dead_reckoning_active"] is True
    assert state.pose.x == pytest.approx(seeded_x + 1.0)
    assert state.pose.y == pytest.approx(seeded_y)


def test_manual_reset_re_zeros_drift_at_current_position(monkeypatch):
    adapter, clock = make_adapter(monkeypatch)
    adapter.set_dead_reckoning(True)
    adapter._handle_message(FakeMsg("ATTITUDE", roll=0.0, pitch=0.0, yaw=math.pi / 2))  # NED 90deg (East) -> ENU yaw=0
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=1.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))
    clock.advance(1000)
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=1.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))
    assert adapter.get_state().pose.x == pytest.approx(1.0)

    adapter.reset_dead_reckoning_origin()
    clock.advance(1000)
    adapter._handle_message(FakeMsg("VFR_HUD", groundspeed=1.0, heading=0, climb=0.0, alt=0.0, airspeed=0.0, throttle=0))
    # First tick after reset only re-establishes the baseline at the
    # position it was reset to (1.0) rather than continuing to accumulate.
    assert adapter.get_state().pose.x == pytest.approx(1.0)
