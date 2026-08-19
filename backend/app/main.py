"""
Unified Robot Gateway — FastAPI app assembly. Owns two background loops:

  control_loop   (settings.control.rate_hz): computes CoordinationState from
                  the latest leader/follower RobotState, safety-clamps and
                  dispatches the resulting command to the follower's
                  adapter, updates MissionState degrade/recover, records
                  telemetry+coordination when an experiment is active, and
                  broadcasts everything to UI WebSocket clients.

  supervisor_loop (settings.supervisor.interval_s): builds a SupervisorContext
                  from current state and calls the active MissionSupervisor,
                  validates its output, and broadcasts/records it.

Everything reachable from routers is built once in GatewayState
(app/state.py) and attached to `app.state.gateway`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import (
    EventSeverity,
    HealthState,
    MissionEvent,
    MissionStateEnum,
    RobotState,
)
from app.routers import experiment_api, health_api, mission_api, robots_api
from app.state import GatewayState
from app.supervisor.validator import validate_recommendation

logger = logging.getLogger("gateway")


async def _control_loop(gw: GatewayState) -> None:
    period = 1.0 / max(1.0, gw.settings.control.rate_hz)
    while True:
        try:
            await _control_tick(gw)
        except Exception:
            logger.exception("control loop tick failed")
        await asyncio.sleep(period)


async def _control_tick(gw: GatewayState) -> None:
    store = gw.telemetry_store
    coord_mgr = gw.coordination_manager
    leader_state = store.robot_states.get(coord_mgr.leader_id) if coord_mgr.leader_id else None
    follower_state = store.robot_states.get(coord_mgr.follower_id) if coord_mgr.follower_id else None

    coordination_state, command = coord_mgr.compute(leader_state, follower_state)
    store.coordination_state = coordination_state

    mission_state = gw.mission_manager.state
    if command is not None and mission_state.state == MissionStateEnum.RUNNING:
        follower_robot = gw.registry.get(command.robot_id)
        result = gw.safety_manager.check_and_clamp(command, follower_state, mission_state.state)
        if result.allowed and follower_robot and follower_robot.adapter:
            await follower_robot.adapter.send_command(result.command)

    if coordination_state.tracking_error_m is not None:
        coord_mgr.record_stabilization(coordination_state.tracking_error_m)

    _update_mission_from_tracking(gw, coordination_state)
    _update_system_health(gw)

    if mission_state.recording and gw.experiment_recorder.active_experiment_id:
        for state in store.robot_states.values():
            gw.experiment_recorder.record_telemetry(state)
        gw.experiment_recorder.record_coordination(coordination_state)

    for state in store.robot_states.values():
        await gw.ws_manager.broadcast("robot_state", state.model_dump(mode="json"))
    await gw.ws_manager.broadcast("coordination_state", coordination_state.model_dump(mode="json"))
    await gw.ws_manager.broadcast("mission_state", gw.mission_manager.state.model_dump(mode="json"))
    await gw.ws_manager.broadcast("system_health", store.system_health.model_dump(mode="json"))


def _update_mission_from_tracking(gw: GatewayState, coordination_state) -> None:
    from app.models import CoordinationTrackingState

    mission_state = gw.mission_manager.state
    if mission_state.state == MissionStateEnum.RUNNING and coordination_state.state == CoordinationTrackingState.LOST:
        gw.mission_manager.degrade()
        gw.telemetry_store.add_event(
            MissionEvent(type="TRACKING_LOST", severity=EventSeverity.WARNING, message="Tracking error exceeded LOST threshold")
        )
    elif mission_state.state == MissionStateEnum.DEGRADED and coordination_state.state == CoordinationTrackingState.TRACKING:
        gw.mission_manager.recover()
        gw.telemetry_store.add_event(MissionEvent(type="TRACKING_RECOVERED", severity=EventSeverity.INFO))


def _update_system_health(gw: GatewayState) -> None:
    store = gw.telemetry_store
    worst = HealthState.NORMAL
    order = {HealthState.NORMAL: 0, HealthState.UNKNOWN: 1, HealthState.WARNING: 2, HealthState.CRITICAL: 3}
    for state in store.robot_states.values():
        if order[state.health] > order[worst]:
            worst = state.health
    if gw.safety_manager.emergency:
        worst = HealthState.CRITICAL
    store.system_health = store.system_health.model_copy(
        update={
            "overall": worst,
            "robots": {rid: s.health for rid, s in store.robot_states.items()},
        }
    )


async def _supervisor_loop(gw: GatewayState) -> None:
    period = max(1.0, gw.settings.supervisor.interval_s)
    while True:
        try:
            await _supervisor_tick(gw)
        except Exception:
            logger.exception("supervisor loop tick failed")
        await asyncio.sleep(period)


async def _supervisor_tick(gw: GatewayState) -> None:
    store = gw.telemetry_store
    context = {
        "robots": {rid: s.model_dump(mode="json") for rid, s in store.robot_states.items()},
        "coordination": store.coordination_state.model_dump(mode="json"),
        "mission": gw.mission_manager.state.model_dump(mode="json"),
        "system_health": store.system_health.overall.value,
    }
    raw = await gw.supervisor.analyze(context)
    recommendation = validate_recommendation(raw)
    store.latest_recommendation = recommendation

    if gw.mission_manager.state.recording and gw.experiment_recorder.active_experiment_id:
        gw.experiment_recorder.record_recommendation(recommendation)

    await gw.ws_manager.broadcast("supervisor_state", recommendation.model_dump(mode="json"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    gw = GatewayState(settings)
    app.state.gateway = gw

    control_task = asyncio.create_task(_control_loop(gw))
    supervisor_task = asyncio.create_task(_supervisor_loop(gw))

    yield

    control_task.cancel()
    supervisor_task.cancel()
    for robot in gw.registry.all():
        if robot.adapter:
            await robot.adapter.disconnect()
    gw.repository.close()


app = FastAPI(title="Heterogeneous Robot Gateway", version="0.2.0", lifespan=lifespan)

_settings_for_cors = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings_for_cors.gateway.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(robots_api.router)
app.include_router(mission_api.router)
app.include_router(experiment_api.router)
app.include_router(health_api.router)


@app.websocket("/ws")
async def ui_websocket(ws: WebSocket) -> None:
    gw: GatewayState = ws.app.state.gateway
    await gw.ws_manager.connect(ws)
    try:
        # Send an initial snapshot so a freshly-opened UI doesn't wait a
        # full control-loop tick for its first paint.
        await ws.send_text(
            json.dumps(
                {
                    "topic": "snapshot",
                    "data": {
                        "robots": {rid: s.model_dump(mode="json") for rid, s in gw.telemetry_store.robot_states.items()},
                        "coordination": gw.telemetry_store.coordination_state.model_dump(mode="json"),
                        "mission": gw.mission_manager.state.model_dump(mode="json"),
                        "systemHealth": gw.telemetry_store.system_health.model_dump(mode="json"),
                        "events": [e.model_dump(mode="json") for e in gw.telemetry_store.recent_events()],
                        "supervisor": gw.telemetry_store.latest_recommendation.model_dump(mode="json")
                        if gw.telemetry_store.latest_recommendation
                        else None,
                    },
                },
                default=str,
            )
        )
        while True:
            # UI clients are receive-only (§46) — we still need to await
            # something to detect disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await gw.ws_manager.disconnect(ws)


@app.websocket("/ws/ingest")
async def ingest_websocket(ws: WebSocket, robot_id: str) -> None:
    """Used by ros_node/turtlebot_bridge_node.py (§10). The ROS2 node
    connects out to us; we never dial in to the robot."""
    gw: GatewayState = ws.app.state.gateway
    robot = gw.registry.get(robot_id)
    if robot is None or robot.adapter is None or not hasattr(robot.adapter, "attach_ws"):
        await ws.close(code=4404, reason=f"Unknown or unarmed TurtleBot adapter: {robot_id}")
        return

    await ws.accept()
    robot.adapter.attach_ws(ws)

    try:
        while True:
            raw = await ws.receive_json()
            if raw.get("type") != "state":
                continue
            state = RobotState.model_validate(raw["state"])
            robot.adapter.ingest_state(state)
    except WebSocketDisconnect:
        pass
    finally:
        robot.adapter.detach_ws()
        gw.registry.mark_disconnected(robot_id)
