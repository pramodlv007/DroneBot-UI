# Research Contribution

## What this is not claiming

None of the following are, individually, novel: web dashboards for
robotics, ROS2 visualization tools, MAVLink telemetry consumption, LLMs
summarizing sensor data, or leader/follower control laws. Each exists in
isolation in many prior systems.

## What this is claiming

> A protocol-agnostic unified supervisory **architecture** for
> heterogeneous aerial-ground robotic teams that normalizes MAVLink UAV
> and ROS2 UGV telemetry into a common semantic robot model, and provides
> real-time coordination, role switching, safety supervision, experimental
> observability, and AI-assisted mission awareness through a single
> interface — with that integration, abstraction, coordination model,
> safety architecture, and evaluation framework as the contribution, not
> any one piece in isolation.

## The five pieces, and why they're evaluated together, not separately

### 1. Heterogeneous robot abstraction

```
MAVLink UAV ──▶ DroneAdapter ─┐
                                ├──▶ Common RobotState ──▶ everything downstream
ROS2 UGV ──▶ TurtleBotAdapter ─┘
```

The concrete, falsifiable claim: a `RobotCard` React component, a
`CoordinationManager.compute()` call, and a SQLite experiment row never
branch on `robot_type`. `docs/common_robot_model.md` documents the schema;
the adapter tests and the live end-to-end verification recorded in this
repository's commit history are the evidence this abstraction holds in
practice, not just on paper.

### 2. Shared coordinate model

```
GPS / MAVLink NED ──▶ mission_map (ENU) ◀── ROS2 odom
```

Both source frames are converted through one centralized, unit-tested
module (`coordinate_transformer.py`) rather than ad hoc per-callsite math
— see `docs/coordinate_frames.md` for the exact conversions and their
sign conventions. This is what makes tracking error, separation, and
bearing between a UAV and a UGV a single well-defined number instead of a
napkin calculation redone differently in three places (which is what the
pre-refactor codebase actually had — see `docs/audit.md`).

### 3. Dynamic, protocol-agnostic leader/follower coordination

`CoordinationManager` derives `DRONE_FOLLOWS_TURTLE` vs.
`TURTLE_FOLLOWS_DRONE` from *which robot type is currently assigned
leader*, not from a hard-coded direction — the same `_go_to_point_command`
control law drives either a differential-drive UGV (linear+angular
velocity) or an omnidirectional UAV follower (ENU velocity vector) from
one shared distance/bearing computation. Role switches are logged with
before/after tracking error and stabilization time
(`RoleSwitchRecord`), which is what turns "the robots can swap roles" into
a measurable claim (RQ4) rather than a demo-only capability.

### 4. Safety-supervised coordination

```
mission command → SafetyManager.check_and_clamp() → RobotAdapter
```

Documented in full in `docs/safety.md`. The contribution here isn't "there
is a safety check" (unremarkable) — it's that the *same* gate sits between
every coordination-derived command and every adapter regardless of
protocol, so adding a third robot type doesn't mean also adding a third
safety implementation.

### 5. AI-assisted, non-actuating mission awareness

```
multi-robot telemetry + coordination + mission + health state
       │
       ▼
  MissionSupervisor.analyze()   (Mock | Disabled | OpenAI | Claude)
       │
       ▼
  validate_recommendation()    ← deterministic, provider-agnostic gate
       │
       ▼
  SupervisorRecommendation (structured, whitelisted action enum)
```

The supervisor is swappable (`backend/app/supervisor/__init__.py::build_supervisor`)
and the rest of the system is provably indifferent to which provider is
active — `DisabledSupervisor` returns a neutral, non-actionable status,
and every code path that reads a recommendation only ever sees the same
`SupervisorRecommendation` type regardless of provider. This is the
concrete answer to RQ5: the deterministic control/safety path
(`SafetyManager`, `MissionManager`) has zero dependency on the supervisor
being enabled, reachable, or fast — verified by `DisabledSupervisor`
being a legitimate, tested configuration, not a stub.

### 6. Synchronized experimental observability

Every one of the above — telemetry, coordination, mission events, role
switches, and AI recommendations — lands in the same SQLite database
keyed by one `experiment_id`, on one shared timeline
(`docs/experiments.md`). This is what makes "did the AI recommendation
happen before or after the tracking-error spike that likely caused it"
answerable from data rather than from operator memory.

## Research Questions

- **RQ1** — Can heterogeneous UAV and UGV telemetry be normalized into a
  common semantic model without significant control-loop overhead?
  *Measurable via*: the `telemetry_latency_ms` field present on every
  `RobotState`, and the control loop's own tick duration (currently
  un-instrumented beyond wall-clock loop period — see roadmap).
- **RQ2** — How much latency does the unified gateway add compared with
  direct communication? *Measurable via*: comparing MAVLink-source→model
  latency and ROS2-source→model latency (both captured per-message) against
  model→UI WebSocket latency (capturable via a UI-side received timestamp
  compared to the gateway's `received_timestamp_ms`, not yet instrumented
  in the frontend — roadmap item).
- **RQ3** — How accurately can the system maintain leader/follower
  coordination across heterogeneous coordinate/communication frameworks?
  *Measurable via*: tracking RMSE, p95 tracking error, mean separation
  (all computed automatically per experiment — `docs/experiments.md`).
- **RQ4** — How quickly can the platform recover from communication
  degradation, disconnects, or role switching? *Measurable via*:
  `mean_stabilization_time_s` after a role switch, and — using fault
  injection (`FaultInjectionRegistry`) — degraded/lost tracking-state
  recovery time under simulated latency/packet-loss/disconnect.
- **RQ5** — Does semantic AI supervision improve operator awareness
  without compromising deterministic control safety? *Measurable via*:
  `llm_recommendation_count`/`mean_llm_latency_ms` per experiment, plus a
  structured A/B comparison (deterministic-only vs.
  deterministic+supervisor experiments, compared via the Experiments
  page) — the safety half of this question is a structural property
  (`docs/safety.md`), not something that needs a metric to prove, since
  there is no code path from a recommendation to an actuator.
- **RQ6** — Can one protocol-agnostic UI support heterogeneous robot types
  without robot-specific frontend redesign? *Measurable via*: the
  concrete test of adding a new `RobotType`/adapter (§58,
  `docs/architecture.md`'s "Extensibility" section) and confirming zero
  changes to `RobotCard`, `MissionMap`, or `CoordinationPanel` are needed.

## Honest limitations

- The equirectangular GPS→ENU approximation (`coordinate_frames.md`) is
  valid for the sub-kilometer operating areas this platform targets, not
  arbitrary distances.
- Per-hop latency instrumentation (RQ1/RQ2) currently stops at
  `telemetry_latency_ms` (source→gateway); UI-side receive timestamps
  aren't yet captured, so the model→UI hop isn't measured end-to-end yet.
- The ROS2 side of this system (`ros_node/`) could not be executed in the
  environment this was built in (no ROS2 install available) — it was
  written to the same interface and message contract the gateway expects
  and is unit-testable in its pure-math parts (`coordinate_transformer`
  import), but the `rclpy` integration itself has not been run against a
  live TurtleBot as part of this work. This is stated plainly rather than
  claimed as verified.
