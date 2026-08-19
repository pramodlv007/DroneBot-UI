from __future__ import annotations

from fastapi import Request

from app.state import GatewayState


def get_gateway(request: Request) -> GatewayState:
    return request.app.state.gateway
