# Development and verification

## Local workflow

Follow the root [README](../README.md) to install dependencies. Use
`DEPLOYMENT_MODE=SIMULATION` for local development; the checked-in system
YAML selects physical mode. No external LLM credentials are needed when the
supervisor is `mock` or `disabled`.

Run from the repository root:

```bash
scripts/run_tests.sh
```

Or run explicitly from the backend directory with its virtual environment:

```bash
cd backend
.venv/bin/python -m pytest tests -q
```

On Windows, use `.venv\Scripts\python.exe`. Keep test collection scoped to
`backend/tests`; root-level `test_drone_data.py` is a legacy hardware utility.

Frontend checks, from `ui/`:

```bash
npm ci
npm test
npm run lint
npm run build
```

`lint` performs TypeScript checking. There is no ESLint configuration.
`npm test` runs 13 Vitest cases for mission readiness and API error messages.
Build output goes to ignored `ui/dist/`.
Backend dependencies are not locked; record Python and package versions
when reproducing an experiment.

## Local review: 2026-09-21

Verified on macOS with Python 3.14.6:

- Backend: 83 tests pass, including 27 added regression cases.
- Frontend: TypeScript check and Vite production build pass.
- In-process simulation API smoke check: robot connections, invalid-role
  rejection, recorded mission start, pause/resume/stop, and experiment listing pass.
- Vite reports chunks exceeding its 500 kB warning threshold.
- Physical robots, ROS2, Docker execution, real LLM requests, and interactive
  browser behavior were not covered by the initial backend review.

The review fixed these behaviors:

| Problem | Result | Regression coverage |
| --- | --- | --- |
| Followers drove toward the leader's position despite configured separation | Both UAV and UGV followers slow and stop at the requested separation | `test_coordination_manager.py` |
| Missing assigned robot samples reported idle tracking | Missing samples report `LOST`, allowing mission degradation | Coordination and gateway regression tests |
| Open ROS2 sockets bypassed telemetry expiration | No-sample and stale-sample connections expire even with an open socket | `test_review_regressions.py` |
| ROS2 receive times came from the remote payload | Gateway stamps its own receive time and rejects another robot's ID | `test_review_regressions.py` |
| Per-axis clamping allowed excessive diagonal speed; NaN could become motion | Horizontal speed is capped as a vector; non-finite commands and wrong-robot states are rejected | `test_safety_manager.py` |
| API accepted one robot as both leader and follower | Start/role request validation rejects identical IDs | `test_review_regressions.py` |
| Example YAML overrides depended on the launch directory | Relative YAML paths resolve from the repository root | `test_review_regressions.py` |
| Documented scripts were non-executable and activation fallback could exit early | Scripts are executable, check activation paths, and support `python3` at setup | Test helper executed successfully |

## Troubleshooting

**Backend virtual environment missing:** create `backend/.venv` and install
`backend/requirements.txt`. The test helper intentionally does not install
packages or connect to hardware.

**No robots listed after copying `.env`:** inspect the YAML override paths.
They resolve from the repository root; confirm the files contain a `robots`
mapping. Restart after changing `.env` or YAML because settings are cached.

**TurtleBot disconnects while its socket is open:** a socket alone does not
prove telemetry is flowing. The ROS2 bridge must continue sending state
samples, even while stationary, within `safety.telemetry_stale_s`.

**Ports already in use:** stop the specific previous development process
or choose another Uvicorn port and update the Vite proxy. Avoid terminating
all Python or Node processes on the machine.

**Mission unexpectedly tries hardware connections:** use
`DEPLOYMENT_MODE=SIMULATION`. `TEST` is not a mock-adapter alias.

**Fault injection returns 403:** physical mode deliberately disables the
fault endpoints. Use simulation for fault experiments.

## Boundaries for future work

The gateway has no API authentication. Some safety configuration fields
are currently descriptive rather than enforced by the command gate; see
[safety.md](safety.md). Simulation tests verify software behavior, not
physical stopping distance or flight-controller behavior.

Keep domain logic in managers, protocol details in adapters, and UI requests
in REST routes. Add a regression that reproduces the failure before changing
control or connection lifecycle behavior. Run the full backend suite and
frontend build before sharing changes.

## UI follow-up

The UI review adds mission readiness guidance, preserves Stop during degraded
tracking, updates roles only after a successful request, and hides recording
indicators after a mission ends. Mode changes require disconnected robots
and an inactive mission; the header mode badge opens setup instead of
silently disconnecting the team. Emergency status is also read from the
backend safety flag, including when the mission itself is already stopped.

Experiment and replay views have loading/error/retry states and ignore late
responses from previous selections. Recording choices are keyboard buttons;
map controls and the replay slider have accessible labels. Navigation,
focus outlines, reduced motion, text contrast, and narrow-screen layouts
have been improved. Physical setup instructions are collapsible.

Browser checks used an isolated simulation gateway and temporary SQLite
file: connected two mocks, selected roles, started/paused/resumed/stopped a
recorded mission, opened experiment details, and played/paused replay.
Connection setup and replay were inspected at a narrow viewport; lower
panels now scroll on shorter desktop windows. These are manual smoke checks,
not automated browser regression tests. Gateway shutdown/restart was also
checked: the UI shows unavailable robot status during the outage and
recovers automatically when the gateway returns.

To run a UI preview against a gateway on a different port:

```bash
GATEWAY_PROXY_TARGET=http://127.0.0.1:8011 npm --prefix ui run dev -- --port 5174
```

The override only changes Vite's development proxy. Production nginx routing
is configured separately in `ui/nginx.conf`.

### Minimal dashboard layout

The mission view now prioritizes the position map, compact robot summaries,
and mission controls. The repeated live telemetry strip is removed from this
view. Detailed telemetry, history, coordination diagnostics, the activity
log, and AI recommendations remain available through expandable sections.
Robot warning/critical health, armed status, and active dead reckoning remain
visible in the compact summary. Neutral styling lives in
`ui/src/styles/minimal.css`, loaded after the existing component styles.

The compact and expanded robot views were checked with simulated robots,
and the mission layout was inspected at a 375px viewport without horizontal
overflow. Frontend tests, type checking, and production build pass.
