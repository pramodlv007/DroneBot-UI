# Coordinate Frames

All frame math is centralized in `backend/app/coordinate_transformer.py`
(pure-stdlib Python, `import math` and `dataclasses` only — no pydantic,
no ROS, no MAVLink) and unit-tested in
`backend/tests/test_coordinate_transformer.py`. Nowhere else in the
codebase should do inline trigonometry on a position or heading. If you
find yourself writing `math.cos`/`math.sin` on a robot pose outside this
module, that's a layering violation — add a function here instead.

## The canonical frame: `mission_map`

Every robot's position is ultimately expressed in one shared frame:

- **x = East (meters)**
- **y = North (meters)**
- **z = Up (meters)**
- **yaw = radians, counter-clockwise from +x (East)** — i.e. standard
  math/ENU convention, matching `atan2(y, x)`. This is deliberately *not*
  compass bearing (0=North, clockwise) — see the conversion functions
  below for the one place that distinction is handled.

This is an ENU (East-North-Up) frame, chosen over NED because it matches
the right-handed convention ROS2/REP-103 already uses for `odom`/`map`,
so only the MAVLink side needs conversion, not both sides.

## Source frames

### 1. GPS / WGS84 (drone, GPS mode)

`lat, lon` (degrees), `alt` (meters). Converted to `mission_map` via an
equirectangular local-tangent-plane approximation anchored at a
`GeoOrigin` (the first GPS fix received, unless explicitly set):

```
meters_per_deg_lat = (pi/180) * EARTH_RADIUS_M
meters_per_deg_lon = meters_per_deg_lat * cos(origin.latitude)

east_m  = (lon - origin.longitude) * meters_per_deg_lon
north_m = (lat - origin.latitude)  * meters_per_deg_lat
```

This is adequate for the sub-kilometer operating areas this platform
targets (the same approximation the legacy bridge used, just centralized
and tested — see `docs/audit.md`). It is **not** valid for areas spanning
many kilometers or near the poles; that would need a proper geodesic
library (e.g. `pyproj`), noted as future work.

### 2. MAVLink `LOCAL_POSITION_NED` (drone, LOCAL mode)

North/East/Down, **left-handed**, relative to wherever the autopilot's EKF
initialized. This is a fixed axis *permutation* (not a rotation) into ENU:

```
x_enu = east
y_enu = north
z_enu = -down
```

Yaw: MAVLink attitude yaw is compass-style (0=North, clockwise-positive
radians). Converted via:

```
enu_yaw = normalize(pi/2 - ned_yaw)
```

### 3. ROS2 odometry (TurtleBot `nav_msgs/Odometry`)

`x` = Forward from the odom origin, `y` = Left, both right-handed (REP-103
compliant) — but the odom origin is wherever the robot booted, which is
**not** the same origin as the drone's GPS/NED frame. Converting this
onto `mission_map` needs:

- **`heading_offset_rad`**: the ENU yaw the TurtleBot's odom +x (front)
  was facing at t=0, i.e. a compass bearing converted once via
  `compass_deg_to_enu_yaw_rad`.
- **`origin_offset_{x,y}_m`**: where the TurtleBot's odom origin sits in
  `mission_map` (defaults to the mission_map origin).

Both are established **once**, at mission start
(`CoordinateTransformer.set_turtlebot_origin`), not re-derived per sample.
Because both odom and mission_map are right-handed, this is a pure
rotation + translation:

```
mission_x = odom_x * cos(H) - odom_y * sin(H) + origin_offset_x
mission_y = odom_x * sin(H) + odom_y * cos(H) + origin_offset_y
mission_yaw = normalize(odom_yaw + H)
```

Contrast this with the legacy bridge's GPS→odom conversion, which used a
**reflection matrix**, not a rotation — that was correct there because it
was converting between a left-handed frame (GPS North/East) and a
right-handed one (odom Forward/Left) directly. Converting odom into the
(also right-handed) `mission_map` frame needs no such reflection.

### Where the heading offset comes from

The legacy bridge had an ambiguous `TURTLEBOT_FACING_DEG` config value
(actually a syntax error — see `docs/audit.md`) with an "auto-detect from
Pixhawk compass" fallback that required physically walking the drone
alongside the TurtleBot at startup. In the decoupled gateway architecture
the TurtleBot doesn't have a colocated compass to borrow, so
`heading_deg_from_north` is now an explicit, always-valid ROS2 launch
parameter (`ros_node/heterogeneous_robot_bridge/launch/turtlebot_bridge.launch.py`,
default `0.0`) that the operator sets once per physical deployment to
match how the robot is actually oriented at boot.

## Quaternion → yaw

Standard extraction (rotation about +z only, which is all a
ground-vehicle or leveled-drone application needs):

```
yaw = atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
```

Implemented once (`yaw_from_quaternion`) and used identically by the
gateway's tests and by `ros_node`'s local copy (see `turtlebot_bridge_node.py`
— it has its own tiny copy of this one function rather than importing the
gateway module for it, since it's a three-line pure-math function used
before any WebSocket connection exists to justify the cross-package
import).

## Sign convention summary

| Quantity | Convention |
|---|---|
| `mission_map` x | East-positive |
| `mission_map` y | North-positive |
| `mission_map` yaw | radians, CCW-positive from East, range (-π, π] |
| Compass bearing (GPS/MAVLink heading) | degrees, CW-positive from North, range [0, 360) |
| MAVLink NED | North/East/Down, left-handed |
| ROS2 odom | Forward/Left/Up, right-handed (REP-103) |

## Testing

`backend/tests/test_coordinate_transformer.py` covers: angle
normalization at the ±π boundary, compass↔ENU yaw conversion at all four
cardinal directions, GPS→ENU at the origin and along each axis, the
NED→ENU axis permutation, MAVLink yaw→ENU yaw at 0° and 90°, quaternion→yaw
at identity and a 90° rotation, the TurtleBot odom→mission_map rotation
(identity case and a facing-North case), bearing/distance helpers, and
`CoordinateTransformer`'s origin-locking behavior (locks on first sample,
does not silently re-anchor on a later one; raises clearly if you try to
convert TurtleBot odom before an origin has been set).
