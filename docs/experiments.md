# Experiments

## Recording

`POST /api/mission/start` with `recording: true` (the default) creates an
experiment row (`ExperimentRecorder.start`, `backend/app/experiment_recorder.py`)
capturing: experiment/mission id, start time, leader/follower robot ids,
whether the LLM supervisor is enabled and which provider, the current git
commit (`git rev-parse --short HEAD`, best-effort), software version, and
a snapshot of the active coordination/safety/control configuration. From
that point until `/api/mission/stop`, every control-loop tick records:

- Every robot's `RobotState` (`telemetry_samples` table)
- The computed `CoordinationState` (`coordination_samples` table)

and every `MissionEvent` and `SupervisorRecommendation` is recorded as it
occurs, plus every logged role switch
(`CoordinationManager.role_switch_log`, persisted via
`ExperimentRecorder.record_role_switch`).

## Storage

SQLite (`backend/app/db.py`), chosen per §5's explicit preference for the
simplest reliable option for a research prototype. Access goes through the
`ExperimentRepository` abstract interface — `mission_api.py`,
`experiment_api.py`, and `experiment_recorder.py` never issue SQL
directly, so swapping to Postgres later is one new class, not a
call-site-by-call-site migration.

## Metrics (§26)

Computed on demand by `ExperimentRecorder.compute_metrics()` from the
recorded `coordination_samples`, `events`, `recommendations`, and
`role_switches` tables — never cached, so they're always consistent with
whatever is currently in the database (including a still-running
experiment, if you query it mid-mission):

| Metric | Computation |
|---|---|
| Tracking RMSE | √(mean(tracking_error²)) over all coordination samples |
| Mean / max / p95 tracking error | Standard statistics over `tracking_error_m` |
| Mean / max separation | Standard statistics over `separation_m` |
| Mean / max latency | Standard statistics over `telemetry_latency_ms` (the *coordination* latency — max of leader/follower telemetry latency at each sample; see `docs/common_robot_model.md` for the per-hop latency fields available in raw telemetry) |
| Mission duration | `ended_at_ms - started_at_ms` |
| Warning / critical event counts | Count of `events` rows by `severity` |
| Role switch count, mean stabilization time | From `role_switches`; stabilization time is filled in by `CoordinationManager.record_stabilization()` the first control-tick after a switch where tracking error drops back under the "degraded" threshold |
| LLM recommendation count, mean LLM latency | From `recommendations`; latency is measured by each `MissionSupervisor` implementation itself (wall-clock around the model call) |

## Export

`GET /api/experiments/{id}/export?format=json` returns every recorded
stream (telemetry, coordination, events, recommendations, role switches)
plus the computed metrics in one document — this is the complete record
of an experiment. `?format=csv` returns a flattened coordination time
series (one row per sample: timestamp, tracking error, separation, heading
error, latency, tracking state) for quick spreadsheet/plotting use; the
full multi-stream data is only in the JSON export.

### rosbag2 / MCAP (documented, not automated)

Per §25, rosbag2/MCAP export was scoped as a target format. It is **not**
implemented as an automated export in this build: writing a `.bag`/`.mcap`
file requires the `rosbag2_py` API, which — like the rest of ROS2 — is not
installable in the environment this backend was authored and tested in
(see the decision log in `docs/audit.md`). The JSON export already
contains every field a bag would need; the conversion is mechanical:

1. For each `telemetry_samples` row, construct a message on
   `/robots/{robot_id}/state` (or your own topic naming) at
   `timestamp_ms`.
2. For each `coordination_samples` row, write to `/coordination/state`.
3. Use `rosbag2_py.SequentialWriter` to serialize both streams into one
   bag, sorted by timestamp.

This is flagged as roadmap work in the README rather than silently
omitted.

## Replay

The UI's Replay page (`ui/src/pages/ReplayPage.tsx`) reads the same
`telemetry`/`coordination` export endpoints, finds the latest sample
at-or-before a scrubbable cursor position per robot, and renders it
through the same local-frame map component the live Mission page uses
(`LocalFrameMap`, exported from `MissionMap.tsx`) — so a replayed mission
looks and behaves identically to a live one, just driven by
`requestAnimationFrame` advancing a cursor through recorded timestamps
instead of a WebSocket. Playback supports 0.5×/1×/2×/4× speed and a
draggable position slider.

## Comparison

The Experiments page lets you mark one experiment "compare" while another
is selected; every chart (tracking error, separation, latency, heading
error vs. time) overlays both series, each on its own recorded
time-since-start axis (so two experiments of different absolute start
times/durations still compare validly). This directly supports the
evaluation scenario in §27: *baseline coordination* vs. *unified gateway*
vs. *unified gateway + AI supervisor*, run as three separate recorded
experiments and compared pairwise.

## Suggested experiment procedures

See `docs/novelty.md`'s Research Questions section for the motivating
questions; the six experiment designs from the brief (baseline tracking,
turning, communication delay via fault injection, packet loss via fault
injection, role switching, LLM supervisor A/B) all reduce to: configure
`config/mission.yaml`/fault injection as needed, `POST /api/mission/start`
with `recording: true`, run the scenario, `POST /api/mission/stop`, then
read `GET /api/experiments/{id}` for metrics or export for raw data.
Curated result sets belong in `experiments/<category>/` (see that
directory's structure — `tracking_accuracy/`, `latency/`, `packet_loss/`,
`role_switching/`, `llm_supervision/`); raw per-run exports are
gitignored by default (see `.gitignore`) so the repository doesn't
accumulate every ad hoc test run.
