"""
Centralized coordinate transformations between the frames used by MAVLink
UAVs, ROS2 UGVs, and the shared `mission_map` frame the UI and coordination
logic operate in. See docs/coordinate_frames.md for the full frame
definitions and sign-convention diagrams — this module is the only place
those conventions should be implemented; nowhere else in the codebase
should do inline trig on positions or headings.

Frame summary
-------------
mission_map (canonical, ENU):
    x = East (m), y = North (m), z = Up (m), yaw = radians, CCW from +x
    (East), i.e. standard math convention, NOT compass bearing.

GPS / WGS84:
    lat, lon (degrees), alt (m). Converted to mission_map via an
    equirectangular local-tangent-plane approximation anchored at a
    configurable origin (`GeoOrigin`). This is adequate for the sub-km
    operating areas this platform targets; anything beyond ~5-10 km from
    the origin should not rely on this approximation.

MAVLink LOCAL_POSITION_NED:
    x = North (m), y = East (m), z = Down (m) — a *left-handed*,
    North-East-Down frame relative to wherever the autopilot's EKF
    initialized. Converted to ENU with `ned_to_enu`.

ROS2 odom (REP-103 compliant, e.g. nav_msgs/Odometry from a TurtleBot):
    x = Forward from odom origin, y = Left, z = Up — right-handed, but its
    origin/heading is wherever the robot booted, which is *not* the same
    origin as the drone's GPS/NED frame. `turtlebot_odom_to_mission_frame`
    re-bases it onto mission_map using one fixed heading offset
    (`heading_offset_rad`, the compass bearing the TurtleBot's +x axis was
    facing at odom-origin time) plus a translation offset
    (`origin_offset_m`, the mission_map position of the TurtleBot's odom
    origin). Both offsets are established once at mission start (see
    `CoordinateTransformer.set_turtlebot_origin`) and are NOT re-derived
    per-sample — do not add per-sample heading correction here.

Yaw convention:
    All yaw values entering or leaving this module are radians, normalized
    to (-pi, pi], measured counter-clockwise from +x (East) — i.e. standard
    math/ENU convention. Compass headings (0=North, 90=East, clockwise) are
    converted at the boundary via `compass_deg_to_enu_yaw_rad` and never
    propagated further into the system as compass degrees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


EARTH_RADIUS_M = 6_371_000.0


def normalize_angle_rad(angle_rad: float) -> float:
    """Wrap to (-pi, pi]. Use this instead of ad hoc while-loops."""
    wrapped = math.atan2(math.sin(angle_rad), math.cos(angle_rad))
    return wrapped


def compass_deg_to_enu_yaw_rad(compass_deg: float) -> float:
    """Compass bearing (0=North, 90=East, clockwise-positive) -> ENU yaw
    (radians, CCW-positive from East). This is the ONE place that
    conversion happens; nothing downstream should see compass degrees."""
    enu_deg = 90.0 - compass_deg
    return normalize_angle_rad(math.radians(enu_deg))


@dataclass(frozen=True)
class GeoOrigin:
    """The lat/lon that maps to mission_map (0, 0)."""

    latitude: float
    longitude: float


def gps_to_enu(lat: float, lon: float, alt: float, origin: GeoOrigin) -> tuple[float, float, float]:
    """Equirectangular local-tangent-plane approximation, anchored at
    `origin`. Returns (x=East_m, y=North_m, z=Up_m aka alt passthrough).

    meters_per_deg_lat is treated as constant (valid globally to within
    ~0.5%); meters_per_deg_lon is scaled by cos(origin latitude) since
    longitude degrees shrink toward the poles.
    """
    meters_per_deg_lat = (math.pi / 180.0) * EARTH_RADIUS_M
    meters_per_deg_lon = meters_per_deg_lat * math.cos(math.radians(origin.latitude))

    east_m = (lon - origin.longitude) * meters_per_deg_lon
    north_m = (lat - origin.latitude) * meters_per_deg_lat
    return east_m, north_m, alt


def ned_to_enu(north: float, east: float, down: float) -> tuple[float, float, float]:
    """MAVLink LOCAL_POSITION_NED (North, East, Down; left-handed) ->
    mission_map ENU (East, North, Up; right-handed).

    This is a fixed axis permutation, not a rotation:
        x_enu = east
        y_enu = north
        z_enu = -down
    """
    return east, north, -down


def ned_yaw_to_enu_yaw(ned_yaw_rad: float) -> float:
    """MAVLink yaw (radians, 0=North, clockwise-positive, matching compass
    convention) -> ENU yaw (radians, 0=East, counter-clockwise-positive)."""
    return normalize_angle_rad((math.pi / 2.0) - ned_yaw_rad)


def yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    """Standard quaternion -> yaw (rotation about +z) extraction, used for
    ROS2 geometry_msgs/Quaternion. Returns radians in (-pi, pi]."""
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return normalize_angle_rad(math.atan2(siny_cosp, cosy_cosp))


@dataclass
class TurtleBotFrameOffset:
    """Established once per mission (see CoordinateTransformer). Maps a raw
    ROS2 odom (x=Forward, y=Left) sample onto mission_map ENU."""

    heading_offset_rad: float   # ENU yaw the TurtleBot's odom +x pointed at t=0
    origin_offset_x_m: float    # mission_map x of the TurtleBot's odom origin
    origin_offset_y_m: float    # mission_map y of the TurtleBot's odom origin


def turtlebot_odom_to_mission_frame(
    odom_x: float, odom_y: float, odom_yaw_rad: float, offset: TurtleBotFrameOffset
) -> tuple[float, float, float]:
    """Rotate+translate a ROS2 odom pose (Forward/Left, right-handed) into
    mission_map ENU (East/North, right-handed) using the fixed heading and
    origin offsets captured at mission start.

    Both source and target frames are right-handed, so this is a pure
    rotation by `heading_offset_rad` followed by a translation — no
    reflection needed here (contrast with GPS->odom in the legacy bridge,
    which *did* need a reflection because GPS's North/East frame is
    left-handed relative to Forward/Left).
    """
    c = math.cos(offset.heading_offset_rad)
    s = math.sin(offset.heading_offset_rad)

    mission_x = odom_x * c - odom_y * s + offset.origin_offset_x_m
    mission_y = odom_x * s + odom_y * c + offset.origin_offset_y_m
    mission_yaw = normalize_angle_rad(odom_yaw_rad + offset.heading_offset_rad)

    return mission_x, mission_y, mission_yaw


def horizontal_distance_m(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def heading_error_deg(bearing_to_target_rad: float, current_yaw_rad: float) -> float:
    """Smallest signed angular error (degrees) to rotate `current_yaw_rad`
    onto `bearing_to_target_rad`, in (-180, 180]."""
    err = normalize_angle_rad(bearing_to_target_rad - current_yaw_rad)
    return math.degrees(err)


def bearing_to_point_rad(from_x: float, from_y: float, to_x: float, to_y: float) -> float:
    """ENU bearing (radians, CCW from +x/East) from one mission_map point to
    another."""
    return normalize_angle_rad(math.atan2(to_y - from_y, to_x - from_x))


class CoordinateTransformer:
    """Stateful convenience wrapper: owns the GeoOrigin (set from the first
    GPS fix, or explicitly) and the TurtleBotFrameOffset (set from the
    first odom sample + a configured/auto-detected heading), so adapters
    don't each re-implement "lock origin on first sample" logic.
    """

    def __init__(self) -> None:
        self._geo_origin: GeoOrigin | None = None
        self._turtle_offset: TurtleBotFrameOffset | None = None

    # -- GPS -------------------------------------------------------------

    @property
    def geo_origin(self) -> GeoOrigin | None:
        return self._geo_origin

    def set_geo_origin(self, latitude: float, longitude: float) -> None:
        self._geo_origin = GeoOrigin(latitude=latitude, longitude=longitude)

    def gps_to_mission_frame(self, lat: float, lon: float, alt: float) -> tuple[float, float, float]:
        if self._geo_origin is None:
            self.set_geo_origin(lat, lon)
        return gps_to_enu(lat, lon, alt, self._geo_origin)

    # -- TurtleBot odom ----------------------------------------------------

    @property
    def turtlebot_offset(self) -> TurtleBotFrameOffset | None:
        return self._turtle_offset

    def set_turtlebot_origin(
        self,
        heading_deg_from_north: float,
        mission_x_m: float = 0.0,
        mission_y_m: float = 0.0,
    ) -> None:
        """Call once, at mission start, with the compass heading the
        TurtleBot's front (odom +x) was facing, and where that point sits
        in mission_map (default: mission_map origin)."""
        self._turtle_offset = TurtleBotFrameOffset(
            heading_offset_rad=compass_deg_to_enu_yaw_rad(heading_deg_from_north),
            origin_offset_x_m=mission_x_m,
            origin_offset_y_m=mission_y_m,
        )

    def turtlebot_odom_to_mission(
        self, odom_x: float, odom_y: float, odom_yaw_rad: float
    ) -> tuple[float, float, float]:
        if self._turtle_offset is None:
            raise RuntimeError(
                "TurtleBot frame origin not set — call set_turtlebot_origin() "
                "before converting odom samples."
            )
        return turtlebot_odom_to_mission_frame(odom_x, odom_y, odom_yaw_rad, self._turtle_offset)
