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
    CoordinationTrackingState,
    EventSeverity,
    HealthState,
    MissionEvent,
    MissionStateEnum,
    RobotState,
    now_ms,
)
from app.routers import experiment_api, health_api, mission_api, robots_api, ai_monitor_api
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

    # ── Staleness watchdog ────────────────────────────────────────────────
    # Any connected robot that has stopped sending telemetry for longer than
    # telemetry_stale_s is considered gone.  We mark it stale (connected=False,
    # state cleared) and emit an event so the UI reflects reality immediately.
    #
    # IMPORTANT: this must use now_ms() (wall clock, the same clock every
    # RobotState/heartbeat timestamp is stamped with) — NOT
    # asyncio.get_event_loop().time(), which is a monotonic clock on an
    # unrelated epoch (process/boot start). Comparing the two produced a
    # meaningless age that was never > the threshold, so this watchdog never
    # actually fired: a robot whose bridge script died or hung without a
    # clean TCP close stayed "connected" forever with frozen/no telemetry.
    stale_threshold_ms = gw.settings.safety.telemetry_stale_s * 1000
    now_ms_val = now_ms()
    for robot in gw.registry.all():
        if not robot.connected:
            continue
        state = store.robot_states.get(robot.robot_id)
        if state is None:
            # If the robot is an ingest robot with an open WebSocket, keep it alive
            if robot.adapter is not None and getattr(robot.adapter, "_ws", None) is not None:
                robot.last_heartbeat_ms = now_ms_val
                continue

            # Connected (bridge socket attached / heartbeat received) but not
            # a single telemetry sample has arrived yet. Give it up to the
            # same stale threshold from the moment it connected, then treat
            # it as a failed connection rather than leaving it stuck
            # "connected" with nothing to show.
            if robot.last_heartbeat_ms is not None and (now_ms_val - robot.last_heartbeat_ms) > stale_threshold_ms:
                logger.warning("Robot %s connected but produced no telemetry — marking disconnected", robot.robot_id)
                stale_adapter = gw.registry.mark_stale(robot.robot_id)
                if stale_adapter is not None:
                    try:
                        await stale_adapter.disconnect()
                    except Exception:
                        pass
                await gw.emit_event(
                    MissionEvent(
                        type="TELEMETRY_NEVER_RECEIVED",
                        severity=EventSeverity.WARNING,
                        robot_ids=[robot.robot_id],
                        message=f"{robot.robot_id} connected but sent no telemetry — marking offline",
                    )
                )
            continue

        # If the robot has an active open WebSocket, don't drop it if stationary
        if robot.adapter is not None and getattr(robot.adapter, "_ws", None) is not None:
            continue

        age_ms = now_ms_val - state.received_timestamp_ms
        if age_ms > stale_threshold_ms:
            logger.warning("Robot %s telemetry stale (%d ms) — marking disconnected", robot.robot_id, age_ms)
            stale_adapter = gw.registry.mark_stale(robot.robot_id)
            if stale_adapter is not None:
                try:
                    await stale_adapter.disconnect()
                except Exception:
                    pass
            # Correct any already-open UI client's cached copy immediately
            # (map/metrics bar), not just future REST polls.
            await gw.clear_robot_telemetry(robot.robot_id)
            await gw.emit_event(
                MissionEvent(
                    type="TELEMETRY_STALE",
                    severity=EventSeverity.WARNING,
                    robot_ids=[robot.robot_id],
                    message=f"{robot.robot_id} telemetry stale ({age_ms:.0f} ms) — marking offline",
                )
            )
    # ─────────────────────────────────────────────────────────────────────

    leader_state = store.robot_states.get(coord_mgr.leader_id) if coord_mgr.leader_id else None
    follower_state = store.robot_states.get(coord_mgr.follower_id) if coord_mgr.follower_id else None

    coordination_state, command = coord_mgr.compute(leader_state, follower_state)

    # ── Mission health score + predictive alerts ──────────────────────
    # Compute mission health score from live data (every tick)
    warning_count = sum(1 for e in store.events if e.severity == EventSeverity.WARNING)
    critical_count = sum(1 for e in store.events if e.severity == EventSeverity.CRITICAL)
    health_score, health_components = coord_mgr.compute_mission_health_score(
        coordination_state, store.robot_states, warning_count, critical_count
    )
    coordination_state.mission_health_score = health_score
    coordination_state.mission_health_components = health_components

    # Emit predictive separation warning (rate-limited: max once per 10s)
    if (
        coordination_state.predicted_tracking_error_m is not None
        and coordination_state.predicted_tracking_error_m >= coord_mgr.tracking_error_degraded_m
        and coordination_state.state == CoordinationTrackingState.TRACKING  # only warn if currently OK
    ):
        # Check rate limit — avoid spamming
        recent_pred_warnings = [
            e for e in list(store.events)[-20:]
            if e.type == "PREDICTED_SEPARATION_WARNING"
        ]
        if not recent_pred_warnings or (now_ms() - recent_pred_warnings[-1].timestamp_ms) > 10_000:
            await gw.emit_event(
                MissionEvent(
                    type="PREDICTED_SEPARATION_WARNING",
                    severity=EventSeverity.WARNING,
                    message=(
                        f"Predicted separation in ~3s: {coordination_state.predicted_separation_m:.1f} m "
                        f"(tracking error {coordination_state.predicted_tracking_error_m:.1f} m) — "
                        f"trend: {coordination_state.separation_trend}"
                    ),
                    value=coordination_state.predicted_separation_m,
                    metadata={
                        "predicted_tracking_error_m": coordination_state.predicted_tracking_error_m,
                        "separation_trend": coordination_state.separation_trend,
                        "current_separation_m": coordination_state.separation_m,
                    },
                )
            )
    # ─────────────────────────────────────────────────────────────────

    store.coordination_state = coordination_state

    mission_state = gw.mission_manager.state

    # ── Anomaly detection ────────────────────────────────────────────────
    # Always-on, independent of any UI tab being open (unlike the AI
    # Monitor's rule engine, which only evaluates while polled).
    anomalies = gw.anomaly_detector.evaluate(
        now_ms_val, store.robot_states, command, mission_state.state == MissionStateEnum.RUNNING
    )
    for anomaly_event in anomalies:
        await gw.emit_event(anomaly_event)
    # ─────────────────────────────────────────────────────────────────────

    if command is not None and mission_state.state == MissionStateEnum.RUNNING:
        follower_robot = gw.registry.get(command.robot_id)
        result = gw.safety_manager.check_and_clamp(command, follower_state, mission_state.state)
        if result.allowed and follower_robot and follower_robot.adapter:
            await follower_robot.adapter.send_command(result.command)

    if coordination_state.tracking_error_m is not None:
        coord_mgr.record_stabilization(coordination_state.tracking_error_m)

    await _update_mission_from_tracking(gw, coordination_state)
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
    await gw.ws_manager.broadcast("anomalies", gw.anomaly_detector.active_anomalies())


async def _update_mission_from_tracking(gw: GatewayState, coordination_state) -> None:
    from app.models import CoordinationTrackingState

    mission_state = gw.mission_manager.state
    if mission_state.state == MissionStateEnum.RUNNING and coordination_state.state == CoordinationTrackingState.LOST:
        gw.mission_manager.degrade()
        await gw.emit_event(
            MissionEvent(type="TRACKING_LOST", severity=EventSeverity.WARNING, message="Tracking error exceeded LOST threshold")
        )
    elif mission_state.state == MissionStateEnum.DEGRADED and coordination_state.state == CoordinationTrackingState.TRACKING:
        gw.mission_manager.recover()
        await gw.emit_event(MissionEvent(type="TRACKING_RECOVERED", severity=EventSeverity.INFO))


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
app.include_router(ai_monitor_api.router)


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
                        "anomalies": gw.anomaly_detector.active_anomalies(),
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
async def ingest_websocket(ws: WebSocket, robot_id: str = "turtlebot_01") -> None:
    """Used by ros_node/turtlebot_bridge_node.py (§10). The ROS2 node
    connects out to us; we never dial in to the robot."""
    gw: GatewayState = ws.app.state.gateway
    robot = gw.registry.get(robot_id)
    if robot is None:
        await ws.close(code=4404, reason=f"Unknown robot: {robot_id}")
        return

    # If the operator hasn't clicked CONNECT in the UI yet, auto-arm the adapter
    if robot.adapter is None or not hasattr(robot.adapter, "attach_ws"):
        from app.adapters.turtlebot_adapter import TurtleBotAdapter
        adapter = TurtleBotAdapter(robot_id, robot.config)
        reg = await adapter.connect()

        def _on_state(state, _gw=gw, _robot_id=robot_id):
            _gw.telemetry_store.update_robot_state(state)
            _gw.registry.update_state(_robot_id, state)

        adapter.set_state_listener(_on_state)
        gw.registry.attach_adapter(robot_id, adapter)
        gw.registry.mark_connected(robot_id, reg)

    await ws.accept()
    robot.adapter.attach_ws(ws)
    if robot.registration:
        gw.registry.mark_connected(robot_id, robot.registration)
    # Seed initial UGV state in telemetry_store so UI and coordination immediately register it
    initial_ugv_state = robot.adapter.get_state()
    if initial_ugv_state:
        # Placeholder only — a zero pose, no velocity/battery. Flag it so the UI
        # says "waiting for /odom" instead of presenting it as live telemetry.
        # The first real state from the bridge replaces it (metadata {}).
        initial_ugv_state = initial_ugv_state.model_copy(update={"metadata": {"awaiting_odom": True}})
        gw.telemetry_store.update_robot_state(initial_ugv_state)
        gw.registry.update_state(robot_id, initial_ugv_state)
    await gw.emit_event(
        MissionEvent(
            type="ROBOT_CONNECTED",
            severity=EventSeverity.INFO,
            robot_ids=[robot_id],
            message=f"{robot_id} ROS2 node attached — live telemetry active",
        )
    )

    # A read timeout on the ingest socket itself: if the ROS2 bridge node's
    # process dies or the network drops without a clean TCP close, receive_json()
    # would otherwise block forever and this robot would show "connected"
    # indefinitely with no telemetry. Bound every read so a dead peer is
    # detected within one stale-threshold window.
    read_timeout_s = gw.settings.safety.telemetry_stale_s
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_json(), timeout=read_timeout_s)
            except asyncio.TimeoutError:
                logger.warning("TurtleBot %s ingest socket silent for %.1fs — closing", robot_id, read_timeout_s)
                await ws.close(code=4408, reason="No telemetry received within timeout")
                break
            if raw.get("type") != "state":
                continue
            state = RobotState.model_validate(raw["state"])
            # A socket that is actively delivering telemetry is the source of
            # truth for connectivity. If a stale disconnect/duplicate socket
            # left the registry saying "offline" or the adapter pointing at a
            # different (closed) socket, heal both — otherwise the robot streams
            # data forever while the UI shows it offline and commands go nowhere.
            if robot.adapter is not None and getattr(robot.adapter, "_ws", ws) is not ws:
                robot.adapter.attach_ws(ws)
            robot.adapter.ingest_state(state)
            if not robot.connected and robot.registration is not None:
                gw.registry.mark_connected(robot_id, robot.registration)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Anything other than a normal disconnect (bad payload, adapter bug)
        # used to vanish silently and just look like "robot went offline".
        logger.exception("Ingest handler for %s failed", robot_id)
    finally:
        if robot.adapter is not None and hasattr(robot.adapter, "detach_ws"):
            robot.adapter.detach_ws()
        gw.registry.mark_disconnected(robot_id)
        await gw.clear_robot_telemetry(robot_id)
        await gw.emit_event(
            MissionEvent(
                type="ROBOT_DISCONNECTED",
                severity=EventSeverity.WARNING,
                robot_ids=[robot_id],
                message=f"{robot_id} ROS2 bridge disconnected",
            )
        )
