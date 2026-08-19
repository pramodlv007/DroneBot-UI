"""REST endpoints for robot connection lifecycle + simulated fault injection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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
    return {
        "robotId": robot.robot_id,
        "robotType": robot.config.type,
        "protocol": robot.config.protocol,
        "displayName": robot.config.display_name,
        "connected": robot.connected,
        "capabilities": robot.registration.capabilities if robot.registration else robot.config.capabilities,
        "lastHeartbeatMs": robot.last_heartbeat_ms,
        "state": robot.last_state.model_dump(mode="json") if robot.last_state else None,
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


@router.post("/{robot_id}/connect")
async def connect_robot(robot_id: str, gw: GatewayState = Depends(get_gateway)):
    robot = gw.registry.get(robot_id)
    if robot is None:
        raise HTTPException(404, f"Unknown robot: {robot_id}")
    if robot.connected:
        return _serialize(robot)

    adapter = _build_adapter(gw, robot_id, robot)
    try:
        registration = await adapter.connect()
    except Exception as exc:
        raise HTTPException(502, f"Failed to connect {robot_id}: {exc}") from exc

    def _on_state(state, _gw=gw, _robot_id=robot_id):
        _gw.telemetry_store.update_robot_state(state)
        _gw.registry.update_state(_robot_id, state)

    adapter.set_state_listener(_on_state)
    gw.registry.attach_adapter(robot_id, adapter)
    gw.registry.mark_connected(robot_id, registration)
    gw.telemetry_store.add_event(
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
    gw.telemetry_store.add_event(
        MissionEvent(type="ROBOT_DISCONNECTED", severity=EventSeverity.WARNING, robot_ids=[robot_id], message=f"{robot_id} disconnected")
    )
    return _serialize(gw.registry.get(robot_id))


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
