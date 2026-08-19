# Safety Architecture

## The rule

Every command that reaches a robot flows through exactly one path:

```
UI request  →  Mission Manager  →  Safety Manager  →  Robot Adapter
```

There is no code path from the UI (or the LLM supervisor) directly to
`adapter.send_command()`. This is enforced structurally, not by
convention: `RobotAdapter.send_command()` is only ever called from two
places in the entire codebase —

1. `backend/app/main.py::_control_tick`, after
   `SafetyManager.check_and_clamp()` has returned `allowed=True`, and
2. `backend/app/routers/mission_api.py::emergency_stop`, which calls it
   directly with a **zero-velocity** `RobotCommand` — the one deliberate
   bypass, discussed below.

The frontend has no function anywhere that constructs a `RobotCommand` or
talks to an adapter — `MissionControls.tsx` only calls REST endpoints
(`/api/mission/start`, `/pause`, `/roles`, `/emergency_stop`, …), and the
gateway derives the actual velocity commands internally from
`CoordinationManager`.

## SafetyManager.check_and_clamp()

Every candidate command is checked, in order, against:

1. **Emergency stop active?** → blocked outright, reason
   `EMERGENCY_STOP_ACTIVE`.
2. **Mission state allows commands?** Only `RUNNING`/`ARMED` do; anything
   else (including `PAUSED`, `DEGRADED`, `EMERGENCY`, `STOPPED`) blocks
   the command.
3. **Robot connected?** → `ROBOT_NOT_CONNECTED` if not.
4. **Telemetry fresh?** (`telemetry_stale_s`, default 2.0s) →
   `TELEMETRY_STALE` if the most recent `RobotState` is older than that.
5. **Command rate limit** (`max_command_rate_hz`, default 20) →
   `COMMAND_RATE_LIMITED` if called again too soon for the same robot.
6. **Velocity clamp**: `linear_x`, `linear_y` clamped to
   `±max_linear_speed_mps`; `angular_z` clamped to
   `±max_angular_speed_radps`. This is the one check that never *rejects*
   — an over-limit command is clamped to the limit rather than dropped,
   because dropping a coordination controller's output entirely (rather
   than saturating it) is worse for stability, not safer.

All five thresholds are configuration (`config/system.yaml` `safety:` /
`config/mission.yaml` `control:`), never hard-coded in `safety_manager.py`.

## Emergency Stop

`POST /api/mission/emergency_stop` does three things, in order:

1. `SafetyManager.trigger_emergency_stop(source, robot_states)` — records
   `active=True`, a timestamp, the triggering source, and a **snapshot of
   every robot's `RobotState` at the moment of trigger** (for post-hoc
   analysis — see `emergency_info()`).
2. `MissionManager.emergency()` — transitions the mission state machine to
   `EMERGENCY` (blocking any future command via check #2 above).
3. Explicitly calls `adapter.send_command()` with a **zero-velocity**
   command for every currently-connected robot, immediately — not relying
   solely on each adapter's own stale-command watchdog to coast to a stop
   over the next second. This is a deliberate, documented bypass of
   `check_and_clamp()`: zero is always within every safety limit, and this
   call *is* the safety action, not a normal mission command competing
   with the gate meant to constrain normal mission commands.

Clearing (`POST /api/mission/emergency_clear`) requires an explicit
operator action; the mission returns to `READY`, not `RUNNING` — a fresh
`/api/mission/start` is required to resume, so an operator can't
accidentally un-pause a mission whose original leader/follower assignment
or thresholds might no longer be appropriate.

The UI makes the emergency state unmistakable: `EmergencyStopButton`
switches to a large, continuously-pulsing red "CLEAR EMERGENCY STOP"
button the instant `mission.state === "EMERGENCY"` arrives over the
WebSocket, and a `confirm()` prompt guards *triggering* it (not clearing
it — clearing should be fast once an operator has verified it's safe to
resume).

## Defense in depth: two independent watchdogs

The gateway's staleness check (#4 above) protects against the gateway
continuing to *issue* commands based on old data. Separately,
`ros_node/turtlebot_bridge_node.py` runs its own 20 Hz local watchdog that
zeroes `/cmd_vel` if it hasn't received a command from the gateway within
1 second — independent of whether the gateway-side check is even running,
so a dropped WebSocket connection between gateway and robot doesn't leave
the TurtleBot coasting on its last command indefinitely. `MockDroneAdapter`
and `MockTurtleBotAdapter` implement the equivalent behavior in
simulation (`COMMAND_FRESH_WINDOW_S`) so the failure mode is
demonstrable without hardware.

## What the LLM supervisor cannot do

See [novelty.md](novelty.md) and `backend/app/supervisor/validator.py`.
Short version: the supervisor returns a `SupervisorRecommendation` from a
fixed enum of high-level actions (`CONTINUE`, `SLOW_DOWN`, `PAUSE`, `STOP`,
`CHECK_GPS`, `CHECK_COMMUNICATION`, `RETURN_TO_SAFE_STATE`) — there is no
code path from a `SupervisorRecommendation` to `adapter.send_command()`
anywhere in the codebase. `validate_recommendation()` additionally
rejects (replaces with a conservative fallback) any recommendation whose
free-text fields contain actuator-level language (`linear_x`, `pwm`,
`cmd_vel`, …), as a second layer of defense against a future change
accidentally treating the LLM's text as more than a display string.

## Configuration reference

```yaml
# config/system.yaml
safety:
  max_tracking_error_m: 3.0
  max_latency_ms: 500
  heartbeat_timeout_s: 2.0
  telemetry_stale_s: 2.0
  max_command_rate_hz: 20
  min_battery_percent: 15
```

```yaml
# config/mission.yaml
control:
  rate_hz: 10
  max_linear_speed_mps: 0.22
  max_angular_speed_radps: 1.0
```

## Fault injection is simulation-only

`POST /api/robots/{id}/fault` (§50) is refused with `403` outright when
`DEPLOYMENT_MODE=PHYSICAL` (checked in `robots_api.py` before touching the
fault registry) — there is no code path by which a fault-injection request
can reach a real robot's adapter. `FaultInjectionRegistry` is only ever
read by `MockDroneAdapter`/`MockTurtleBotAdapter`.
