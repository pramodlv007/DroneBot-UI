from __future__ import annotations

from fastapi import APIRouter, Depends

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
