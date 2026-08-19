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

"Connect" for this adapter means "start accepting an ingest connection for
this robot_id"; `connected` only becomes true once the ROS2 node actually
attaches and starts pushing state.
"""

from __future__ import annotations

import asyncio
from typing import Optional

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
        self._state = RobotState(
            robot_id=robot_id,
            robot_type=RobotType.UGV,
            protocol=Protocol.ROS2,
            connected=False,
            pose=RobotPose(),
            health=HealthState.UNKNOWN,
        )

    async def connect(self) -> RobotRegistration:
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
        self._state = self._state.model_copy(update={"connected": False})

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

    def detach_ws(self) -> None:
        self._ws = None
        self._state = self._state.model_copy(update={"connected": False})

    def ingest_state(self, state: RobotState) -> None:
        self._state = state
        self._emit(state)

    @property
    def armed(self) -> bool:
        return self._armed
