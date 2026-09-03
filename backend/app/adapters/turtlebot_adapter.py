"""
TurtleBot (ROS2) adapter — ingest side.

Unlike DroneAdapter, this adapter does not reach out to the robot itself:
the robot's companion computer runs ros_node/turtlebot_bridge_node.py,
which is a plain rclpy node that connects OUT to this gateway's
`/ws/ingest` WebSocket endpoint (see app/websocket.py) and pushes already
frame-converted RobotState JSON, and receives RobotCommand JSON back over
the same socket to publish as /cmd_vel.

This keeps the gateway from needing inbound network reachability to the
robot (which is often on a separate, firewalled robot LAN), and keeps
rclpy entirely out of the backend process — nothing here imports ROS2.

**Connection semantics**: calling `connect()` only opens/arms the ingest
slot — `RegisteredRobot.connected` stays False until the ROS2 node
actually attaches and starts pushing state over `/ws/ingest`.  The caller
must pass `on_connect_cb` so the registry can be notified on physical
attach rather than on adapter construction.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from app.config import RobotConfig
from app.models import (
    HealthState,
    Protocol,
    RobotCapability,
    RobotCommand,
    RobotPose,
    RobotRegistration,
    RobotState,
    RobotType,
)

from .base import RobotAdapter


class TurtleBotAdapter(RobotAdapter):
    def __init__(self, robot_id: str, config: RobotConfig) -> None:
        self.robot_id = robot_id
        self.config = config
        self._armed = False
        self._ws = None  # starlette WebSocket, set by websocket.py on attach
        self._on_connect_cb: Optional[Callable[[], None]] = None
        self._last_ingest_ms: int = 0
        self._state = RobotState(
            robot_id=robot_id,
            robot_type=RobotType.UGV,
            protocol=Protocol.ROS2,
            connected=False,
            pose=RobotPose(),
            health=HealthState.UNKNOWN,
        )

    def set_on_connect_cb(self, cb: Callable[[], None]) -> None:
        """Register a callback fired when the ROS2 node physically attaches."""
        self._on_connect_cb = cb

    async def connect(self) -> RobotRegistration:
        """
        Arms the ingest slot.  Does NOT set connected=True — that only
        happens in attach_ws() when the ROS2 bridge node actually dials in.
        """
        self._armed = True
        return RobotRegistration(
            robot_id=self.robot_id,
            robot_type=RobotType.UGV,
            protocol=Protocol.ROS2,
            display_name=self.config.display_name,
            capabilities=[RobotCapability(c) for c in self.config.capabilities],
            supported_commands=["velocity"],
        )

    async def disconnect(self) -> None:
        self._armed = False
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._state = self._state.model_copy(update={"connected": False, "health": HealthState.UNKNOWN})

    def get_state(self) -> RobotState:
        return self._state

    async def send_command(self, command: RobotCommand) -> None:
        if self._ws is None:
            return
        await self._ws.send_json(
            {
                "type": "command",
                "linear_x": command.linear_x,
                "angular_z": command.angular_z,
            }
        )

    # -- called by app/websocket.py's ingest route -------------------------

    def attach_ws(self, ws) -> None:
        self._ws = ws
        # Now the robot is truly connected — notify the registry
        self._state = self._state.model_copy(update={"connected": True, "health": HealthState.UNKNOWN})
        if self._on_connect_cb is not None:
            try:
                self._on_connect_cb()
            except Exception:
                pass

    def detach_ws(self) -> None:
        self._ws = None
        self._state = self._state.model_copy(update={"connected": False, "health": HealthState.UNKNOWN})

    def ingest_state(self, state: RobotState) -> None:
        self._last_ingest_ms = int(time.time() * 1000)
        self._state = state
        self._emit(state)

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def last_ingest_ms(self) -> int:
        return self._last_ingest_ms
