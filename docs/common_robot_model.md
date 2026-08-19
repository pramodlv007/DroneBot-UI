# The Common Robot Model

This is the core abstraction the whole platform is built around (§4, §7).
No component above the adapter layer — coordination logic, safety, the
experiment recorder, the LLM supervisor, or the frontend — is allowed to
know whether a given `RobotState` came from MAVLink or ROS2.

## Canonical definition

The Python/pydantic definition in `backend/app/models.py` is the source of
truth. `ui/src/types/robot.ts` is a hand-maintained mirror (see the note at
the top of that file for why it isn't code-generated, and what to check if
the two drift).

```python
class RobotState(BaseModel):
    robot_id: str
    robot_type: RobotType          # UAV | UGV | MANIPULATOR | QUADRUPED | OTHER
    protocol: Protocol             # MAVLink | ROS2 | Mock

    connected: bool
    mode: Optional[str]
    health: HealthState            # NORMAL | WARNING | CRITICAL | UNKNOWN

    pose: RobotPose                 # x, y, z, roll, pitch, yaw — all in mission_map ENU
    gps: Optional[GPSState]
    velocity: Optional[VelocityState]
    battery: Optional[BatteryState]

    capabilities: list[RobotCapability]

    source_timestamp_ms: int        # when the underlying message was produced
    received_timestamp_ms: int      # when the gateway/adapter observed it

    metadata: dict[str, Any]
```

`telemetry_latency_ms` is a computed property
(`received_timestamp_ms - source_timestamp_ms`), not a stored field — this
guarantees it can never silently go stale relative to the two timestamps
it's derived from.

## Why both timestamps (§56)

Every adapter stamps `source_timestamp_ms` as close to the original event
as it can (the MAVLink adapter uses the moment it parses the message off
the wire; the ROS2 node uses the moment it receives the odometry
callback), and `received_timestamp_ms` is stamped by whichever process
first turns the raw message into a `RobotState`. This makes end-to-end
latency a *real measurement*, derivable at every hop (MAVLink→model,
ROS2→model, model→UI), rather than an estimate — which directly answers
RQ2 (latency overhead of the unified gateway) with actual data instead of
a guess.

## Normalization responsibilities per adapter

| Adapter | Source messages | Normalization performed |
|---|---|---|
| `DroneAdapter` | `GLOBAL_POSITION_INT`, `LOCAL_POSITION_NED`, `ATTITUDE`, `VFR_HUD`, `SYS_STATUS`, `GPS_RAW_INT`, `HEARTBEAT` | GPS→ENU or NED→ENU position (via `coordinate_transformer`), MAVLink yaw (compass-style)→ENU yaw, battery voltage/percent, GPS fix quality→`HealthState` |
| `TurtleBotAdapter` (ingest) | JSON pushed by `ros_node`, already normalized there | Pass-through validation only — all frame math already happened on the robot side, using the *same* `coordinate_transformer` module |
| `MockDroneAdapter` / `MockTurtleBotAdapter` | Internal simulation state | Synthesizes plausible GPS/odometry directly in mission_map coordinates |

## Capabilities, not robot-type branching

The frontend never does `if robot_type == "UAV"`. `RobotCard` renders a
field if it's present (`s.gps && <>...</>`), and `MissionControls` only
offers commands consistent with what `RobotCapability` values a robot
registered with. This is what makes §58 ("add a robot type without
frontend redesign") true rather than aspirational — a quadruped adapter
that reports `ODOMETRY` + `BATTERY` capabilities and omits `gps` renders
correctly in the exact same `RobotCard` component with zero changes.

## Deliberately excluded from the common model

- Raw MAVLink message structs, `sensor_msgs`/`nav_msgs` ROS types, or
  anything protocol-specific — these live only inside `backend/app/adapters/`
  and (for ROS2) `ros_node/`.
- Actuator-level values as anything other than the narrow `RobotCommand`
  (`linear_x`, `linear_y`, `angular_z`) — see [safety.md](safety.md) for
  why this is deliberately the *only* command shape allowed past the
  Safety Manager.
