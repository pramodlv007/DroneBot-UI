# DroneBot UI

A web dashboard and Python gateway for supervising a Pixhawk drone and a
ROS2 TurtleBot through a shared robot model. It supports live telemetry,
leader/follower coordination, mission controls, advisory LLM supervision,
and SQLite experiment recording, export, and replay.

Simulation runs without robots, ROS2, or API keys. Physical operation uses
MAVLink for the drone and an outbound WebSocket bridge from the TurtleBot.

## Quick start (simulation)

Prerequisites: Python with `venv` and pip, Node.js with npm, and two terminals.
The local checks documented in [development.md](docs/development.md) used
Python 3.14.6. The Docker backend uses Python 3.11. Frontend dependencies
are pinned by `ui/package-lock.json`; use Node.js 22+.

From the repository root on macOS/Linux:

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
cp .env.example .env
```

Start the backend:

```bash
DEPLOYMENT_MODE=SIMULATION scripts/dev_backend.sh
```

In a second terminal:

```bash
cd ui
npm ci
npm run dev
```

Open [the dashboard](http://localhost:5173). Connect both robots, select
separate leader and follower robots, then start a mission. Leave recording
enabled to save the run. Stop the mission and use **Experiments** or
**Replay** to inspect the results.

The gateway exposes [interactive API documentation](http://localhost:8000/docs).
Vite proxies `/api` and `/ws` to port 8000.

For Windows PowerShell, replace the backend setup/start commands with:

```powershell
py -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
$env:DEPLOYMENT_MODE = "SIMULATION"
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The frontend commands are the same on Windows.

## Repository layout

| Path | Purpose |
| --- | --- |
| `backend/app/` | FastAPI routes, robot adapters, coordination, safety, persistence, supervisor |
| `backend/tests/` | Backend unit and regression tests |
| `ui/` | React, TypeScript, Vite, Zustand, Recharts, and MapLibre dashboard |
| `ros_node/` | ROS2 `heterogeneous_robot_bridge` package for the TurtleBot |
| `config/` | Robot connections, mission/control parameters, system settings |
| `docs/` | Architecture, operation, development, and research notes |
| `experiments/` | Categories for curated experiment results |
| `scripts/` | Local backend/frontend launch and backend test helpers |

Root-level bridge and LLM scripts are legacy utilities. The maintained
application entry point is `backend/app/main.py`; see the
[historical audit](docs/audit.md) for migration context. `test_drone_data.py`
is a hardware utility, so run the backend test directory explicitly.

## Configuration

Copy `.env.example` to `.env`; keep credentials out of Git.

| Setting | Location | Meaning |
| --- | --- | --- |
| Robot IDs and connections | `config/robots.yaml` | MAVLink endpoint/baud and ROS2 identity/topics |
| Separation and tracking thresholds | `config/mission.yaml` | Leader/follower coordination |
| Speed and control-loop limits | `config/mission.yaml` | Linear speed, yaw rate, loop rate |
| Freshness and command rate | `config/system.yaml` | Telemetry timeout and command gate |
| Supervisor provider | `config/system.yaml` | `mock`, `disabled`, `openai`, or `claude` |
| Database path | `config/system.yaml` | SQLite file, relative to the backend process working directory |
| Deployment mode | `DEPLOYMENT_MODE` in environment/`.env` | Overrides `mode` in `config/system.yaml` |
| Provider credentials/models | `.env` | Used only by the selected LLM provider |
| YAML path overrides | `.env` | `ROBOTS_CONFIG_PATH`, `MISSION_CONFIG_PATH`, `SYSTEM_CONFIG_PATH` |

Relative YAML override paths resolve from the repository root, regardless
of the working directory. Absolute paths are supported for containers.
Restart the backend after editing configuration. Connection settings edited
in the UI apply in memory and are not written back to YAML.

**The checked-in `config/system.yaml` selects `PHYSICAL`.** The backend
helper script explicitly defaults to `SIMULATION`, and the example `.env`
and Docker Compose also select simulation. Set `DEPLOYMENT_MODE` explicitly
when launching Uvicorn directly. `TEST` currently uses the physical adapter
selection path; use `SIMULATION` for hardware-free work.

The helper launches on port 8000. For another address/port, invoke Uvicorn
with `--host`/`--port` and update `ui/vite.config.ts` proxy targets. The
example environment file contains only settings the application consumes.

## How coordination works

Adapters normalize telemetry into `RobotState` in the shared ENU mission
frame. The coordination manager derives a follower velocity, which the
safety manager validates before dispatch. The follower slows as it reaches
`target_separation_m` and stops at or inside that distance; it does not
reverse to restore separation if already too close. A minimum 0.25 m stop
distance also applies.

Missing telemetry from an assigned robot produces `LOST` tracking. The
gateway expires stale telemetry even when a robot's WebSocket remains open.
The safety gate rejects non-finite commands and mismatched robot identities,
and limits the magnitude of horizontal velocity plus angular velocity.

The LLM supervisor supplies displayed recommendations; it does not command
robots. See [safety.md](docs/safety.md) for the command path and watchdogs.

## Physical robots

Read [coordinate_frames.md](docs/coordinate_frames.md) and
[safety.md](docs/safety.md), and configure robot connections before use.
The gateway and UI can run on a host separate from the TurtleBot.

```bash
DEPLOYMENT_MODE=PHYSICAL scripts/dev_backend.sh
```

On the TurtleBot companion computer, with a compatible ROS2 installation:

```bash
cd ros_node
colcon build --packages-select heterogeneous_robot_bridge
source install/setup.bash
ros2 launch heterogeneous_robot_bridge turtlebot_bridge.launch.py \
  robot_id:=turtlebot_01 \
  gateway_ws_url:=ws://GATEWAY_HOST:8000/ws/ingest \
  heading_deg_from_north:=0
```

Replace `GATEWAY_HOST` with the gateway address and `0` with the robot's
actual starting compass heading. The ROS2 package requires `rclpy`,
`nav_msgs`, `sensor_msgs`, `geometry_msgs`, and Python `websockets`.
The gateway connects directly to the drone's configured MAVLink endpoint.
Physical hardware and ROS2 execution were not validated in this local review.

## Docker simulation

```bash
docker compose up --build
```

The UI is served at [localhost:5173](http://localhost:5173), with nginx
proxying to the backend. Compose mounts configuration read-only and stores
SQLite data in the `backend_data` named volume. A full container run was not
part of the current verification.

## Tests and documentation

```bash
scripts/run_tests.sh
cd ui
npm test
npm run lint
npm run build
```

See [development.md](docs/development.md) for verification results,
regression coverage, and troubleshooting. `npm test` checks mission readiness
and API error formatting; lint/build validate TypeScript and production output.

- [Architecture](docs/architecture.md)
- [Common robot model](docs/common_robot_model.md)
- [Coordinate frames](docs/coordinate_frames.md)
- [Safety and watchdogs](docs/safety.md)
- [Experiment workflow and metrics](docs/experiments.md)
- [Research motivation and limitations](docs/novelty.md)
- [Historical audit](docs/audit.md)

## License

The ROS2 package declares Apache-2.0 in its `package.xml`. There is no
top-level license file establishing a repository-wide license.
