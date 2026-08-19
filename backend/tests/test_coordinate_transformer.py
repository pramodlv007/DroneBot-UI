import math

import pytest

from app.coordinate_transformer import (
    CoordinateTransformer,
    GeoOrigin,
    bearing_to_point_rad,
    compass_deg_to_enu_yaw_rad,
    gps_to_enu,
    heading_error_deg,
    horizontal_distance_m,
    ned_to_enu,
    ned_yaw_to_enu_yaw,
    normalize_angle_rad,
    turtlebot_odom_to_mission_frame,
    yaw_from_quaternion,
    TurtleBotFrameOffset,
)


def test_normalize_angle_wraps_into_range():
    assert normalize_angle_rad(0.0) == pytest.approx(0.0)
    assert normalize_angle_rad(2 * math.pi) == pytest.approx(0.0, abs=1e-9)
    assert normalize_angle_rad(3 * math.pi) == pytest.approx(-math.pi, abs=1e-9) or normalize_angle_rad(3 * math.pi) == pytest.approx(math.pi, abs=1e-9)
    assert -math.pi < normalize_angle_rad(10.0) <= math.pi


@pytest.mark.parametrize(
    "compass_deg,expected_enu_deg",
    [
        (0, 90),     # North -> ENU 90deg (i.e. +y)
        (90, 0),     # East -> ENU 0deg (+x)
        (180, -90),  # South -> ENU -90deg (-y)
        (270, -180),  # West -> ENU +/-180deg (-x); atan2's (-pi, pi] range picks -180
    ],
)
def test_compass_to_enu_yaw(compass_deg, expected_enu_deg):
    result = compass_deg_to_enu_yaw_rad(compass_deg)
    assert math.degrees(result) == pytest.approx(expected_enu_deg, abs=1e-6)


def test_gps_to_enu_origin_is_zero():
    origin = GeoOrigin(latitude=37.4275, longitude=-122.1697)
    x, y, z = gps_to_enu(origin.latitude, origin.longitude, 10.0, origin)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)
    assert z == 10.0


def test_gps_to_enu_north_increases_y_east_increases_x():
    origin = GeoOrigin(latitude=0.0, longitude=0.0)
    # ~0.001 deg north
    x, y, _ = gps_to_enu(0.001, 0.0, 0.0, origin)
    assert y > 0
    assert x == pytest.approx(0.0, abs=1e-6)

    x2, y2, _ = gps_to_enu(0.0, 0.001, 0.0, origin)
    assert x2 > 0
    assert y2 == pytest.approx(0.0, abs=1e-6)


def test_ned_to_enu_axis_permutation():
    # NED: North=5, East=3, Down=2 -> ENU: East=3, North=5, Up=-2
    x, y, z = ned_to_enu(north=5.0, east=3.0, down=2.0)
    assert (x, y, z) == (3.0, 5.0, -2.0)


def test_ned_yaw_to_enu_yaw_matches_compass_conversion():
    # MAVLink yaw of 0 (facing North) should match compass 0 -> ENU 90deg
    assert math.degrees(ned_yaw_to_enu_yaw(0.0)) == pytest.approx(90.0, abs=1e-6)
    # MAVLink yaw of pi/2 (facing East) -> ENU 0deg
    assert math.degrees(ned_yaw_to_enu_yaw(math.pi / 2)) == pytest.approx(0.0, abs=1e-6)


def test_yaw_from_quaternion_identity_is_zero():
    assert yaw_from_quaternion(0, 0, 0, 1) == pytest.approx(0.0, abs=1e-9)


def test_yaw_from_quaternion_90deg_about_z():
    # quaternion for +90 deg rotation about Z: (0, 0, sin(45deg), cos(45deg))
    q = (0.0, 0.0, math.sin(math.radians(45)), math.cos(math.radians(45)))
    yaw = yaw_from_quaternion(*q)
    assert math.degrees(yaw) == pytest.approx(90.0, abs=1e-4)


def test_turtlebot_odom_to_mission_frame_zero_offset_is_identity():
    offset = TurtleBotFrameOffset(heading_offset_rad=0.0, origin_offset_x_m=0.0, origin_offset_y_m=0.0)
    x, y, yaw = turtlebot_odom_to_mission_frame(2.0, 1.0, 0.3, offset)
    assert (x, y, yaw) == pytest.approx((2.0, 1.0, 0.3))


def test_turtlebot_odom_to_mission_frame_facing_north_maps_forward_to_plus_y():
    # TurtleBot's odom +x (forward) was facing compass North at t=0.
    heading = compass_deg_to_enu_yaw_rad(0)  # North -> ENU 90deg
    offset = TurtleBotFrameOffset(heading_offset_rad=heading, origin_offset_x_m=0.0, origin_offset_y_m=0.0)
    x, y, _ = turtlebot_odom_to_mission_frame(1.0, 0.0, 0.0, offset)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0, abs=1e-9)


def test_horizontal_distance_and_bearing():
    assert horizontal_distance_m(0, 0, 3, 4) == pytest.approx(5.0)
    bearing = bearing_to_point_rad(0, 0, 1, 0)
    assert math.degrees(bearing) == pytest.approx(0.0, abs=1e-6)  # due East
    bearing_n = bearing_to_point_rad(0, 0, 0, 1)
    assert math.degrees(bearing_n) == pytest.approx(90.0, abs=1e-6)  # due North


def test_heading_error_deg_smallest_signed_angle():
    # Target bearing 170deg, current yaw -170deg: raw difference is 340deg,
    # which normalizes to the much shorter -20deg turn (340 - 360 = -20),
    # not the 340deg long way around.
    err = heading_error_deg(math.radians(170), math.radians(-170))
    assert err == pytest.approx(-20.0, abs=1e-6)


class TestCoordinateTransformer:
    def test_gps_origin_locks_on_first_sample(self):
        ct = CoordinateTransformer()
        assert ct.geo_origin is None
        x, y, _ = ct.gps_to_mission_frame(37.4, -122.1, 5.0)
        assert (x, y) == pytest.approx((0.0, 0.0))
        assert ct.geo_origin is not None

        # A later, different fix should NOT re-anchor the origin.
        x2, y2, _ = ct.gps_to_mission_frame(37.401, -122.1, 5.0)
        assert y2 > 0

    def test_turtlebot_frame_requires_origin_before_conversion(self):
        ct = CoordinateTransformer()
        with pytest.raises(RuntimeError):
            ct.turtlebot_odom_to_mission(1.0, 0.0, 0.0)

        ct.set_turtlebot_origin(heading_deg_from_north=90, mission_x_m=5.0, mission_y_m=5.0)
        x, y, _ = ct.turtlebot_odom_to_mission(0.0, 0.0, 0.0)
        assert (x, y) == pytest.approx((5.0, 5.0))
