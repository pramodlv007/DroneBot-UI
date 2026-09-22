"""
REST endpoints for mission control. Every one of these is the ONLY path
from the UI into MissionManager/CoordinationManager/SafetyManager — the UI
never talks to a RobotAdapter directly (§15).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from app.mission_manager import InvalidTransitionError, MissionStateEnum
from app.models import EventSeverity, MissionEvent, RobotCommand
from app.state import GatewayState

from .deps import get_gateway

router = APIRouter(prefix="/api/mission", tags=["mission"])


class SetRolesRequest(BaseModel):
    leader_id: str
    follower_id: str

    @model_validator(mode="after")
    def distinct_robots(self):
        if self.leader_id == self.follower_id:
            raise ValueError("Leader and follower must be different robots")
        return self


class StartMissionRequest(SetRolesRequest):
    mission_id: str | None = None
    recording: bool = True
    experiment_name: str | None = None


class EmergencyStopRequest(BaseModel):
    source: str = "operator"


@router.get("")
async def get_mission(gw: GatewayState = Depends(get_gateway)):
    return gw.mission_manager.state.model_dump(mode="json")


@router.post("/start")
async def start_mission(body: StartMissionRequest, gw: GatewayState = Depends(get_gateway)):
    leader = gw.registry.get(body.leader_id)
    follower = gw.registry.get(body.follower_id)
    if leader is None or follower is None:
        raise HTTPException(404, "leader_id/follower_id must reference registered robots")
    if not leader.connected or not follower.connected:
        raise HTTPException(409, "Both leader and follower must be connected before starting a mission")

    if gw.safety_manager.emergency:
        raise HTTPException(409, "Cannot start mission while EMERGENCY STOP is active")

    current = gw.mission_manager.state.state
    if current in (MissionStateEnum.RUNNING, MissionStateEnum.PAUSED, MissionStateEnum.DEGRADED):
        raise HTTPException(
            409,
            f"Mission is already {current.value} (id={gw.mission_manager.state.mission_id}). "
            "Call /api/mission/stop before starting a new one.",
        )

    robot_types = {rid: gw.registry.robot_type(rid) for rid in (body.leader_id, body.follower_id)}
    gw.coordination_manager.set_roles(body.leader_id, body.follower_id, robot_types)

    try:
        if gw.mission_manager.state.state in (
            MissionStateEnum.DISCONNECTED,
            MissionStateEnum.STOPPED,
            MissionStateEnum.COMPLETED,
        ):
            gw.mission_manager.ready()
        if gw.mission_manager.state.state == MissionStateEnum.READY:
            gw.mission_manager.transition(MissionStateEnum.ARMED)
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc

    mission_id = body.mission_id or f"MISSION_{uuid.uuid4().hex[:8].upper()}"
    experiment_id = None
    if body.recording:
        experiment_id = f"EXP_{uuid.uuid4().hex[:8].upper()}"
        gw.experiment_recorder.start(
            experiment_id=experiment_id,
            name=body.experiment_name or mission_id,
            mission_id=mission_id,
            leader_id=body.leader_id,
            follower_id=body.follower_id,
            llm_enabled=gw.settings.supervisor.provider not in ("disabled", ""),
            llm_provider=gw.settings.supervisor.provider,
            config={
                "coordination": gw.settings.coordination.model_dump(),
                "safety": gw.settings.safety.model_dump(),
                "control": gw.settings.control.model_dump(),
            },
        )

    try:
        state = gw.mission_manager.start(mission_id, experiment_id, body.recording)
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc

    await gw.emit_event(
        MissionEvent(
            type="MISSION_STARTED",
            severity=EventSeverity.INFO,
            robot_ids=[body.leader_id, body.follower_id],
            message=f"Mission {mission_id} started: leader={body.leader_id}, follower={body.follower_id}",
        )
    )
    return state.model_dump(mode="json")


@router.post("/pause")
async def pause_mission(gw: GatewayState = Depends(get_gateway)):
    try:
        state = gw.mission_manager.pause()
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    gw.coordination_manager.pause()
    await gw.emit_event(MissionEvent(type="MISSION_PAUSED", severity=EventSeverity.INFO))
    return state.model_dump(mode="json")


@router.post("/resume")
async def resume_mission(gw: GatewayState = Depends(get_gateway)):
    try:
        state = gw.mission_manager.resume()
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    robot_types = {r.robot_id: gw.registry.robot_type(r.robot_id) for r in gw.registry.all()}
    gw.coordination_manager.resume(robot_types)
    await gw.emit_event(MissionEvent(type="MISSION_RESUMED", severity=EventSeverity.INFO))
    return state.model_dump(mode="json")


@router.post("/stop")
async def stop_mission(gw: GatewayState = Depends(get_gateway)):
    try:
        state = gw.mission_manager.stop()
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    if gw.mission_manager.state.recording:
        gw.experiment_recorder.stop(status="COMPLETED")
    await gw.emit_event(MissionEvent(type="MISSION_STOPPED", severity=EventSeverity.INFO))
    return state.model_dump(mode="json")


@router.post("/emergency_stop")
async def emergency_stop(body: EmergencyStopRequest, gw: GatewayState = Depends(get_gateway)):
    robot_states = gw.telemetry_store.robot_states
    gw.safety_manager.trigger_emergency_stop(body.source, robot_states)
    try:
        gw.mission_manager.emergency()
    except InvalidTransitionError:
        pass  # already terminal/emergency; the safety flag is what actually matters

    # Explicitly command zero velocity to every connected robot right now,
    # rather than relying solely on each adapter's own stale-command
    # watchdog to coast to a stop. Zero is always within safety limits, so
    # this bypasses SafetyManager.check_and_clamp deliberately — this *is*
    # the safety action, not a normal mission command.
    for robot in gw.registry.all():
        if robot.connected and robot.adapter is not None:
            await robot.adapter.send_command(RobotCommand(robot_id=robot.robot_id, source="safety_manager.emergency_stop"))

    await gw.emit_event(
        MissionEvent(type="EMERGENCY_STOP", severity=EventSeverity.CRITICAL, message=f"Triggered by {body.source}")
    )
    return {"mission": gw.mission_manager.state.model_dump(mode="json"), "emergency": gw.safety_manager.emergency_info()}


@router.post("/emergency_clear")
async def clear_emergency(gw: GatewayState = Depends(get_gateway)):
    gw.safety_manager.clear_emergency_stop()
    try:
        gw.mission_manager.ready()
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    await gw.emit_event(MissionEvent(type="EMERGENCY_CLEARED", severity=EventSeverity.INFO))
    return gw.mission_manager.state.model_dump(mode="json")


@router.post("/roles")
async def set_roles(body: SetRolesRequest, gw: GatewayState = Depends(get_gateway)):
    """Dynamic leader/follower role switching mid-mission (§13)."""
    leader = gw.registry.get(body.leader_id)
    follower = gw.registry.get(body.follower_id)
    if leader is None or follower is None:
        raise HTTPException(404, "leader_id/follower_id must reference registered robots")

    current_tracking_error = gw.telemetry_store.coordination_state.tracking_error_m
    robot_types = {rid: gw.registry.robot_type(rid) for rid in (body.leader_id, body.follower_id)}
    gw.coordination_manager.set_roles(body.leader_id, body.follower_id, robot_types, current_tracking_error)

    await gw.emit_event(
        MissionEvent(
            type="ROLE_SWITCH",
            severity=EventSeverity.INFO,
            robot_ids=[body.leader_id, body.follower_id],
            message=f"Roles switched: leader={body.leader_id}, follower={body.follower_id}",
        )
    )
    return {"leaderId": body.leader_id, "followerId": body.follower_id, "mode": gw.coordination_manager.mode.value}
