from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models import HealthState
from app.state import GatewayState

from .deps import get_gateway

router = APIRouter(prefix="/api/health", tags=["health"])

_SEVERITY_ORDER = {HealthState.NORMAL: 0, HealthState.UNKNOWN: 1, HealthState.WARNING: 2, HealthState.CRITICAL: 3}


@router.get("")
async def get_health(gw: GatewayState = Depends(get_gateway)):
    robot_health = {rid: state.health.value for rid, state in gw.telemetry_store.robot_states.items()}
    worst = HealthState.NORMAL
    for state in gw.telemetry_store.robot_states.values():
        if _SEVERITY_ORDER[state.health] > _SEVERITY_ORDER[worst]:
            worst = state.health
    if gw.safety_manager.emergency:
        worst = HealthState.CRITICAL

    return {
        "overall": worst.value,
        "backend": "NORMAL",
        "robots": robot_health,
        "supervisorProvider": gw.supervisor.provider_name,
        "emergency": gw.safety_manager.emergency,
        "deploymentMode": gw.settings.deployment_mode,
        "missionState": gw.mission_manager.state.state.value,
    }


VALID_MODES = {"SIMULATION", "TEST", "PHYSICAL"}


class ModeUpdate(BaseModel):
    mode: str


@router.patch("/mode")
async def set_deployment_mode(body: ModeUpdate, gw: GatewayState = Depends(get_gateway)):
    """Switch SIMULATION <-> PHYSICAL at runtime without restarting the backend.
    Only affects adapters built on the *next* CONNECT call — currently-connected
    robots keep their existing adapter until disconnected.
    Fault injection endpoints are still blocked in PHYSICAL mode."""
    mode = body.mode.upper()
    if mode not in VALID_MODES:
        raise HTTPException(400, f"Invalid mode '{mode}'. Must be one of: {sorted(VALID_MODES)}")
    if mode != "SIMULATION" and gw.registry.all() and any(r.connected for r in gw.registry.all()):
        raise HTTPException(
            409,
            "Disconnect all robots before switching to PHYSICAL mode to avoid mixing simulated and real adapters.",
        )
    gw.settings = gw.settings.model_copy(update={"deployment_mode": mode})
    return {"deploymentMode": gw.settings.deployment_mode}
