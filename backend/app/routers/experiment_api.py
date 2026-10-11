from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse

from app.state import GatewayState

from .deps import get_gateway

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("")
async def list_experiments(gw: GatewayState = Depends(get_gateway)):
    return gw.repository.list_experiments()


@router.get("/{experiment_id}")
async def get_experiment(experiment_id: str, gw: GatewayState = Depends(get_gateway)):
    experiment = gw.repository.get_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(404, f"Unknown experiment: {experiment_id}")
    metrics = gw.experiment_recorder.compute_metrics(experiment_id)
    return {"experiment": experiment, "metrics": asdict(metrics)}


@router.get("/{experiment_id}/telemetry")
async def get_experiment_telemetry(experiment_id: str, robot_id: str | None = None, gw: GatewayState = Depends(get_gateway)):
    return gw.repository.get_telemetry(experiment_id, robot_id)


@router.get("/{experiment_id}/coordination")
async def get_experiment_coordination(experiment_id: str, gw: GatewayState = Depends(get_gateway)):
    return gw.repository.get_coordination(experiment_id)


@router.get("/{experiment_id}/events")
async def get_experiment_events(experiment_id: str, gw: GatewayState = Depends(get_gateway)):
    return gw.repository.get_events(experiment_id)


@router.get("/{experiment_id}/recommendations")
async def get_experiment_recommendations(experiment_id: str, gw: GatewayState = Depends(get_gateway)):
    return gw.repository.get_recommendations(experiment_id)


@router.get("/{experiment_id}/export")
async def export_experiment(
    experiment_id: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    gw: GatewayState = Depends(get_gateway),
):
    exp = gw.repository.get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(404, f"Unknown experiment: {experiment_id}")
    name = exp.get("name") or exp.get("mission_id") or experiment_id
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(name))
    if format == "csv":
        filename = f"{safe_name}_{experiment_id}.csv"
        return PlainTextResponse(
            gw.experiment_recorder.export_csv(experiment_id),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    filename = f"{safe_name}_{experiment_id}.json"
    data = gw.experiment_recorder.export_json(experiment_id)
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
