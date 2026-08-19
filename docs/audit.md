# Repository Audit — Pre-Refactor Baseline

Snapshot of the repository as of commit `07f08d7` (2026-08-18), before the
heterogeneous supervisory platform refactor. This document is historical: it
describes the *old* flat-script system, not the current architecture. See
[architecture.md](architecture.md) for the current design.

## Inventory

| File | Role | Lines |
|---|---|---|
| `drone_to_turtlebot_bridge.py` | Main bridge: MAVLink drone reader + ROS2 node driving TurtleBot toward drone position | 524 |
| `mavlink_forwarder.py` | Reads Pixhawk over serial, re-broadcasts raw MAVLink bytes over UDP to TurtleBot host | 50 |
| `pc_turtlebot_pixhawk_bridge.py` | Reverse path: receives TurtleBot position over UDP, optionally commands Pixhawk via `SET_POSITION_TARGET_LOCAL_NED` | 146 |
| `turtlebot_sender.py` | ROS2 node: publishes `/odom` position to PC over UDP; listens for "turn commands" | 105 |
| `drone_llm.py` | Ollama (local LLM) telemetry analyzer, blocking loop | 71 |
| `drone_llm_openai.py` | OpenAI telemetry analyzer + yaw-based turn detector, sends turn commands via UDP | 150 |
| `drone_llm_openai_benchmark.py` | Same as above + TTFT/tokens-per-sec benchmarking | 170 |
| `test_drone_data.py` | Debug utility: dumps raw MAVLink messages | 24 |

No `requirements.txt`, no package manifest, no tests, no CI, no `.env.example` (referenced in README but absent), no ROS2 package structure (`package.xml`/`setup.py`) — these are loose scripts meant to be run manually.

## Existing Architecture

Two independent, non-interoperating pipelines, each a single monolithic script mixing I/O, transport, control logic, and (sometimes) LLM calls:

**Forward path (UAV → UGV):**
`Pixhawk --MAVLink(serial/UDP)--> drone_to_turtlebot_bridge.py --ROS2 rclpy--> TurtleBot /cmd_vel`, with `mavlink_forwarder.py` as an optional relay when the Pixhawk is wired to a separate Windows PC rather than directly reachable from the TurtleBot host.

**Reverse path (UGV → UAV):**
`TurtleBot /odom --ROS2 rclpy--> turtlebot_sender.py --UDP/JSON--> pc_turtlebot_pixhawk_bridge.py --MAVLink--> Pixhawk SET_POSITION_TARGET_LOCAL_NED`.

**LLM supervision:** three separate, copy-pasted scripts (`drone_llm.py`, `drone_llm_openai.py`, `drone_llm_openai_benchmark.py`) each independently connect to the Pixhawk and poll telemetry — there is no shared telemetry source or supervisor interface. `drone_llm_openai.py` additionally does double duty as a yaw-based "turn detector" that pushes raw turn commands to the TurtleBot over UDP, bypassing the main bridge entirely — a third, undocumented control path.

## Current Data Flows

- MAVLink telemetry (`GLOBAL_POSITION_INT`, `LOCAL_POSITION_NED`, `ATTITUDE`, `VFR_HUD`, `SYS_STATUS`, `GPS_RAW_INT`) read via `pymavlink`, polled non-blocking inside a `threading.Thread` (`DroneReader` in the main bridge).
- GPS lat/lon converted to local meters using an equirectangular approximation anchored to the first fix received (`home_lat`/`home_lon`), not a proper ENU/geodetic library.
- TurtleBot odometry read via `nav_msgs/Odometry` subscription; yaw extracted manually from quaternion (`yaw_from_quaternion`), not `tf_transformations`.
- Reverse-path position data is serialized to raw JSON over a bare UDP socket (`turtlebot_sender.py` → `pc_turtlebot_pixhawk_bridge.py`), unauthenticated, unencrypted, no schema.
- Turn "commands" are a third ad hoc JSON-over-UDP channel (`drone_llm_openai.py` → `turtlebot_sender.py`'s `command_listener`).

## Current Control Flows

- `DroneToTurtleBotNode.control_loop` runs at `CONTROL_RATE_HZ` (10 Hz) and directly computes and publishes `Twist` to `/cmd_vel` — there is no intermediate safety layer; the go-to-point controller's output is clamped only by `MAX_LINEAR_SPEED`/`MAX_ANGULAR_SPEED` constants inline in the control function.
- Stale-telemetry protection exists but is minimal: a 2-second timeout on both drone and TurtleBot state stops the robot, hard-coded inline (not configurable, not reusable, not exposed anywhere).
- No mission state machine — behavior is governed by a handful of booleans (`_tracking_active`, `ENABLE_TURTLEBOT_MOTION`) and free-floating instance attributes set with `hasattr`/`getattr` (`_heading_rad`, `turtle_home`), which is fragile and hard to reason about.
- No emergency stop concept beyond `KeyboardInterrupt` in `main()`.
- Reverse path (`pc_turtlebot_pixhawk_bridge.py`) has arm/takeoff/guided-mode logic gated behind `ENABLE_DRONE_COMMANDS`/`ARM_AND_TAKEOFF` flags defaulting to `False` — a sensible safety default, but the gating is a raw boolean, not a reviewable safety policy.

## Current Protocols

- **MAVLink** via `pymavlink.mavutil`, connection string configurable (`udp:0.0.0.0:14550` or a COM port), but the string is a hard-coded module constant in every script, duplicated 8 times with different values.
- **ROS2 / rclpy**, `Odometry` in, `Twist` out, default topic names, no namespacing (breaks with more than one TurtleBot).
- **Raw UDP + `json.dumps`** for both the reverse position path and the turn-command path — no versioning, no auth, no framing beyond one-packet-per-message.

## Known Problems / Blockers (found during this audit)

1. **`drone_to_turtlebot_bridge.py:48` — `TURTLEBOT_FACING_DEG = ` has no right-hand side.** This is a `SyntaxError`; the file cannot be imported or run at all in its current state. This was the top-priority fix.
2. **`turtlebot_sender.py`'s `command_listener` never publishes to `/cmd_vel`.** It parses incoming turn commands and only prints them; the actual `Twist` publish is left as a commented-out `TODO` block (lines 43–50). The reverse turn-relay path is a no-op today.
3. Three duplicate MAVLink-connect-and-poll loops (`drone_llm.py`, `drone_llm_openai.py`, `drone_llm_openai_benchmark.py`) each open their own serial connection to the same Pixhawk — running two of these simultaneously will conflict over the serial port.
4. `drone_llm_openai.py` and `_benchmark.py` reference `OPENAI_MODEL = "gpt-5.5"` / `MODEL = "gpt-4.1"` — inconsistent, and `gpt-5.5` is not a real model id; likely a placeholder that was never updated.
5. `pc_turtlebot_pixhawk_bridge.py` binds a UDP socket with no source validation — any host on the network can inject fake TurtleBot positions that (if `ENABLE_DRONE_COMMANDS=True`) directly drive `SET_POSITION_TARGET_LOCAL_NED` on a real aircraft.
6. Hard-coded private IPs (`10.134.169.81`, `10.215.31.111`) and COM ports (`COM10`) baked into source in 5 different files — unusable outside the original author's LAN without editing code.
7. `mavlink_forwarder.py` rebroadcasts the entire raw MAVLink stream over UDP with no filtering — bandwidth-inefficient and forwards command/parameter traffic that a downstream telemetry consumer has no business seeing.
8. GPS→local conversion uses a flat-earth equirectangular approximation with no unit test and no documented sign convention (only a README comment) — the "reflection matrix" (`drone_to_turtlebot_bridge.py:395-398`) is a legitimate and correct way to handle the GPS(NE, left-handed)→odom(FL, right-handed) mismatch, but it is inlined once and undocumented anywhere near the code itself.
9. No reconnection logic anywhere — `master.wait_heartbeat()` blocks forever on connect with no timeout/retry, and no script recovers from a dropped MAVLink or ROS2 connection without a manual restart.
10. `drone_to_turtlebot_bridge.py` line 1 imports `from openai.types.responses import web_search_tool` — unused, vestigial import copy-pasted from another file, never referenced.

## Safety Risks

- No deterministic safety layer between "intent" (LLM, UDP command, or control-loop output) and actuation — commands reach `/cmd_vel` or `SET_POSITION_TARGET_LOCAL_NED` straight out of ad hoc logic.
- LLM output in `drone_to_turtlebot_bridge.py`'s `LLMSupervisor` is printed only today (not actuated), which is safe by accident, not by design — there is no validator preventing a future change from wiring LLM text directly into motor commands.
- Reverse-path UDP listener (`pc_turtlebot_pixhawk_bridge.py`) has no sender authentication, so a spoofed packet can (when enabled) command a real aircraft.
- No emergency-stop primitive exists anywhere in the codebase.
- No velocity-limit enforcement outside the single go-to-point branch of the forward bridge (the `ATTITUDE`/tilt-to-drive branch has its own separate, slightly different clamping logic — duplicated, and easy to let drift out of sync).

## Technical Debt

- Global mutable module-level constants used as configuration everywhere; no config file, no env var loading, no validation.
- Business logic (control law), transport (UDP/MAVLink/ROS2), and presentation (`print`) are all interleaved in the same functions.
- `hasattr`/`getattr`-based "lazy initialization" of instance state (`turtle_home`, `_heading_rad`, `_tracking_active`) instead of an explicit state machine.
- No shared data model between the drone and TurtleBot representations — `DroneState` and `TurtleState` are two unrelated dataclasses with no common interface, and the reverse path re-invents a third shape (`{x, y, yaw}` dict) for the same concept.
- No tests of any kind.

## Reusable Components

These pieces of logic are correct and worth carrying into the new architecture, relocated into proper adapters/modules rather than rewritten from scratch:

- The **GPS→ENU reflection-matrix conversion** (`drone_to_turtlebot_bridge.py:438-443`) — correct handling of the NE(left-handed)/FL(right-handed) mismatch; becomes the seed of `coordinate_transformer.py`.
- The **quaternion→yaw extraction** (`yaw_from_quaternion`) — standard formula, reusable as-is (or swapped for `tf_transformations`).
- The **yaw-wraparound normalization** (`atan2(sin(Δ), cos(Δ))` pattern used in both the bridge and the turn detector) — becomes a shared `normalize_angle()` utility.
- The **MAVLink message-interval request pattern** (`MAV_CMD_SET_MESSAGE_INTERVAL` for `LOCAL_POSITION_NED`/`ATTITUDE`/`VFR_HUD`/`SYS_STATUS`) — correct and becomes part of `DroneAdapter.connect()`.
- The **yaw-delta turn-detection threshold logic** in `drone_llm_openai.py` — useful as an *event* (not a direct actuation path) in the new event timeline.
- The **TTFT/tokens-per-second benchmarking approach** in `drone_llm_openai_benchmark.py` — reusable as the LLM-latency measurement strategy in the experiment metrics layer.

## Components Rewritten / Replaced

- All 8 scripts' direct MAVLink/UDP/ROS2 wiring is superseded by `DroneAdapter` / `TurtleBotAdapter` behind a common `RobotState` model — no UI or coordination code will speak MAVLink or `nav_msgs/Odometry` again.
- The three duplicate LLM scripts are replaced by one `MissionSupervisor` interface with swappable backends (Mock/Disabled/OpenAI/Claude) that only ever emits structured, whitelisted recommendations — never raw commands.
- Raw UDP/JSON position and turn-command channels are replaced by the FastAPI/WebSocket gateway with typed schemas.
- Inline booleans/`hasattr` state are replaced by an explicit `MissionState` state machine and a `SafetyManager` that gates every outbound command.

## Decision Log (architectural choices made for the rewrite)

- **Gateway transport:** FastAPI + WebSockets instead of `rosbridge_suite`. Rationale: the Windows development/authoring environment used for this refactor has no ROS2 install, so a gateway that must be buildable/testable here cannot depend on `rosbridge`. The TurtleBot-side ROS2 node (`ros_node/`) still speaks native rclpy topics on the robot/companion computer, and pushes normalized state to the gateway over a plain WebSocket client — decoupling "runs where ROS2 is installed" from "runs where the UI/backend is installed." This satisfies §5's "you may combine both approaches if architecturally justified."
- **ROS2 custom `.msg`/`.srv` package:** deferred. Authoring a colcon package (`msg/RobotState.msg`, `srv/StartMission.srv`, …) requires a ROS2 toolchain to generate interfaces and cannot be validated in this environment. The common model is instead defined once in Python (`backend/app/models.py`, pydantic) and mirrored in TypeScript (`ui/src/types/`); the ROS2 node imports the same normalization functions and sends JSON, not custom message types. If/when this is deployed on a real ROS2 host, generating the equivalent `.msg` package is straightforward future work (tracked in `docs/architecture.md` roadmap) and does not change the wire contract used by the UI.
- **Charting library:** Recharts (§5 required a justified choice). Reasoning: React-native API (no imperative canvas wiring like uPlot), sufficient performance for the data rates here (≤10 Hz per series, dashboards with a handful of concurrent series), and a smaller bundle/complexity footprint than ECharts for line/area time-series charts, which is all this UI needs.
- **Persistence:** SQLite via a repository interface (`ExperimentRepository`), per §5's explicit preference, swappable for Postgres later without touching call sites.
