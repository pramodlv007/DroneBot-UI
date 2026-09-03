"""REST endpoints for robot connection lifecycle + simulated fault injection."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.adapters.drone_adapter import DroneAdapter
from app.adapters.mock_drone_adapter import MockDroneAdapter
from app.adapters.mock_turtlebot_adapter import MockTurtleBotAdapter
from app.adapters.turtlebot_adapter import TurtleBotAdapter
from app.fault_injection import FaultProfile, fault_injection_registry
from app.models import EventSeverity, MissionEvent, RobotType
from app.state import GatewayState

from .deps import get_gateway

router = APIRouter(prefix="/api/robots", tags=["robots"])


def _serialize(robot) -> dict:
    dr_supported = robot.adapter is not None and hasattr(robot.adapter, "set_dead_reckoning")
    return {
        "robotId": robot.robot_id,
        "robotType": robot.config.type,
        "protocol": robot.config.protocol,
        "displayName": robot.config.display_name,
        "connected": robot.connected,
        "capabilities": robot.registration.capabilities if robot.registration else robot.config.capabilities,
        "lastHeartbeatMs": robot.last_heartbeat_ms,
        "state": robot.last_state.model_dump(mode="json") if robot.last_state else None,
        # Connection parameters, so the UI can show/edit what's currently
        # configured without reading config/robots.yaml directly. Never
        # includes anything secret — these are addresses/ports, not
        # credentials.
        "connection": {
            "connection": robot.config.connection,
            "baud": robot.config.baud,
            "targetSystem": robot.config.target_system,
            "targetComponent": robot.config.target_component,
            "namespace": robot.config.namespace,
        },
        # Indoor/GPS-denied dead-reckoning tracking (UAV/MAVLink only —
        # TurtleBots already get GPS-free position from wheel odometry).
        # "supported" lets the UI hide the control entirely for robot types
        # that don't have it, rather than showing a button that always
        # errors.
        "deadReckoning": {
            "supported": dr_supported,
            "enabled": robot.adapter.dead_reckoning_enabled if dr_supported and robot.connected else False,
            "active": bool(robot.last_state.metadata.get("dead_reckoning_active")) if robot.last_state else False,
        },
    }


@router.get("")
async def list_robots(gw: GatewayState = Depends(get_gateway)):
    return [_serialize(r) for r in gw.registry.all()]


@router.get("/{robot_id}")
async def get_robot(robot_id: str, gw: GatewayState = Depends(get_gateway)):
    robot = gw.registry.get(robot_id)
    if robot is None:
        raise HTTPException(404, f"Unknown robot: {robot_id}")
    return _serialize(robot)


def _build_adapter(gw: GatewayState, robot_id: str, robot):
    simulate = gw.settings.deployment_mode == "SIMULATION"
    robot_type = robot.config.type

    if simulate:
        if robot_type == RobotType.UAV.value:
            return MockDroneAdapter(robot_id, robot.config.display_name)
        return MockTurtleBotAdapter(robot_id, robot.config.display_name)

    if robot.config.protocol == "MAVLink":
        return DroneAdapter(robot_id, robot.config)
    if robot.config.protocol == "ROS2":
        return TurtleBotAdapter(robot_id, robot.config)

    raise HTTPException(400, f"Unsupported protocol for {robot_id}: {robot.config.protocol}")


class RobotConnectionUpdate(BaseModel):
    """Fields an operator can edit from the UI's connection settings
    panel, instead of hand-editing config/robots.yaml and restarting the
    gateway. Only takes effect for adapters built after the update — a
    currently-connected robot must be disconnected first."""

    connection: str | None = None       # MAVLink: "COM10", "udp:0.0.0.0:14550", ...
    baud: int | None = None             # MAVLink serial baud rate
    target_system: int | None = None
    target_component: int | None = None
    namespace: str | None = None        # ROS2: informational, for the launch-command helper


@router.patch("/{robot_id}/config")
async def update_robot_config(robot_id: str, body: RobotConnectionUpdate, gw: GatewayState = Depends(get_gateway)):
    robot = gw.registry.get(robot_id)
    if robot is None:
        raise HTTPException(404, f"Unknown robot: {robot_id}")
    if robot.connected:
        raise HTTPException(409, f"Disconnect {robot_id} before changing its connection settings")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    robot.config = robot.config.model_copy(update=updates)
    return _serialize(robot)


@router.post("/{robot_id}/connect")
async def connect_robot(robot_id: str, gw: GatewayState = Depends(get_gateway)):
    robot = gw.registry.get(robot_id)
    if robot is None:
        raise HTTPException(404, f"Unknown robot: {robot_id}")
    if robot.connected:
        return _serialize(robot)

    adapter = _build_adapter(gw, robot_id, robot)

    def _on_state(state, _gw=gw, _robot_id=robot_id):
        _gw.telemetry_store.update_robot_state(state)
        _gw.registry.update_state(_robot_id, state)

    adapter.set_state_listener(_on_state)

    try:
        registration = await adapter.connect()
    except Exception as exc:
        raise HTTPException(502, f"Failed to connect {robot_id}: {exc}") from exc

    gw.registry.attach_adapter(robot_id, adapter)

    # TurtleBotAdapter is ingest-only: connected=True only fires when the
    # ROS2 bridge node physically attaches via /ws/ingest.  All other
    # adapters (MAVLink drone, mocks) establish a real connection inside
    # adapter.connect() so we can mark them connected immediately.
    if hasattr(adapter, "set_on_connect_cb"):
        # Capture registration in closure so callback has it
        _reg = registration

        async def _emit_connected_event():
            await gw.emit_event(
                MissionEvent(
                    type="ROBOT_CONNECTED",
                    severity=EventSeverity.INFO,
                    robot_ids=[robot_id],
                    message=f"{robot_id} ROS2 node attached — live telemetry active",
                )
            )

        def _on_ros2_attach(_gw=gw, _robot_id=robot_id, _reg=_reg):
            _gw.registry.mark_connected(_robot_id, _reg)
            # Schedule the async event emission back on the event loop
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(_emit_connected_event())
            except RuntimeError:
                pass

        adapter.set_on_connect_cb(_on_ros2_attach)
        # Emit an "armed" event so the UI knows the slot is open
        await gw.emit_event(
            MissionEvent(
                type="ROBOT_ARMED",
                severity=EventSeverity.INFO,
                robot_ids=[robot_id],
                message=f"{robot_id} armed — waiting for ROS2 bridge node to connect",
            )
        )
    else:
        gw.registry.mark_connected(robot_id, registration)
        init_state = adapter.get_state()
        if init_state:
            _on_state(init_state)
        await gw.emit_event(
            MissionEvent(type="ROBOT_CONNECTED", severity=EventSeverity.INFO, robot_ids=[robot_id], message=f"{robot_id} connected")
        )

    return _serialize(gw.registry.get(robot_id))


@router.post("/{robot_id}/disconnect")
async def disconnect_robot(robot_id: str, gw: GatewayState = Depends(get_gateway)):
    robot = gw.registry.get(robot_id)
    if robot is None:
        raise HTTPException(404, f"Unknown robot: {robot_id}")
    if robot.adapter:
        await robot.adapter.disconnect()
    gw.registry.mark_disconnected(robot_id)
    await gw.emit_event(
        MissionEvent(type="ROBOT_DISCONNECTED", severity=EventSeverity.WARNING, robot_ids=[robot_id], message=f"{robot_id} disconnected")
    )
    return _serialize(gw.registry.get(robot_id))


class DeadReckoningUpdate(BaseModel):
    enabled: bool


@router.post("/{robot_id}/dead-reckoning")
async def set_dead_reckoning(robot_id: str, body: DeadReckoningUpdate, gw: GatewayState = Depends(get_gateway)):
    """Toggle indoor/GPS-denied dead-reckoning position tracking for a UAV.
    Only meaningful while connected — there's no adapter instance to hold
    the setting otherwise."""
    robot = gw.registry.get(robot_id)
    if robot is None:
        raise HTTPException(404, f"Unknown robot: {robot_id}")
    if robot.adapter is None or not hasattr(robot.adapter, "set_dead_reckoning"):
        raise HTTPException(400, f"{robot_id} does not support dead reckoning (connect a UAV first)")

    robot.adapter.set_dead_reckoning(body.enabled)
    await gw.emit_event(
        MissionEvent(
            type="DEAD_RECKONING_TOGGLED",
            severity=EventSeverity.INFO,
            robot_ids=[robot_id],
            message=f"{robot_id} indoor dead-reckoning tracking {'enabled' if body.enabled else 'disabled'}",
        )
    )
    return _serialize(robot)


@router.post("/{robot_id}/dead-reckoning/reset")
async def reset_dead_reckoning(robot_id: str, gw: GatewayState = Depends(get_gateway)):
    """Re-zero the drift-accumulating dead-reckoning estimate at the
    vehicle's current position — use when it's physically at a known
    reference point."""
    robot = gw.registry.get(robot_id)
    if robot is None:
        raise HTTPException(404, f"Unknown robot: {robot_id}")
    if robot.adapter is None or not hasattr(robot.adapter, "reset_dead_reckoning_origin"):
        raise HTTPException(400, f"{robot_id} does not support dead reckoning (connect a UAV first)")

    robot.adapter.reset_dead_reckoning_origin()
    await gw.emit_event(
        MissionEvent(
            type="DEAD_RECKONING_RESET",
            severity=EventSeverity.INFO,
            robot_ids=[robot_id],
            message=f"{robot_id} dead-reckoning origin reset to current position",
        )
    )
    return _serialize(robot)


@router.post("/{robot_id}/fault")
async def inject_fault(robot_id: str, fault: dict, gw: GatewayState = Depends(get_gateway)):
    """§50/§51: fault injection is a SIMULATION/TEST-only research tool and
    is refused outright in PHYSICAL mode — there is no code path here that
    can reach a real robot."""
    if gw.settings.deployment_mode == "PHYSICAL":
        raise HTTPException(403, "Fault injection is disabled in PHYSICAL deployment mode")
    profile = FaultProfile(**fault)
    fault_injection_registry.set(robot_id, profile)
    return {"robotId": robot_id, "fault": profile.__dict__}


@router.post("/{robot_id}/fault/clear")
async def clear_fault(robot_id: str, gw: GatewayState = Depends(get_gateway)):
    if gw.settings.deployment_mode == "PHYSICAL":
        raise HTTPException(403, "Fault injection is disabled in PHYSICAL deployment mode")
    fault_injection_registry.clear(robot_id)
    return {"robotId": robot_id, "fault": FaultProfile().__dict__}
