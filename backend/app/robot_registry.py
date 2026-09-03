"""
Robot Registry — tracks every configured robot, its adapter instance,
connection status, capabilities, and last-known state. The UI renders
robot cards purely from what this registry reports; it never hard-codes
"exactly two robots" anywhere.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from app.adapters.base import RobotAdapter
from app.config import RobotConfig
from app.models import (
    HealthState,
    Protocol,
    RobotCapability,
    RobotRegistration,
    RobotState,
    RobotType,
)


@dataclass
class RegisteredRobot:
    robot_id: str
    config: RobotConfig
    adapter: Optional[RobotAdapter] = None
    registration: Optional[RobotRegistration] = None
    last_state: Optional[RobotState] = None
    last_heartbeat_ms: Optional[int] = None
    connected: bool = False


class RobotRegistry:
    def __init__(self, robot_configs: dict[str, RobotConfig]) -> None:
        self._robots: dict[str, RegisteredRobot] = {
            rid: RegisteredRobot(robot_id=rid, config=cfg) for rid, cfg in robot_configs.items()
        }

    def all(self) -> list[RegisteredRobot]:
        return list(self._robots.values())

    def get(self, robot_id: str) -> Optional[RegisteredRobot]:
        return self._robots.get(robot_id)

    def declare(self, robot_id: str, config: RobotConfig) -> RegisteredRobot:
        """Register a robot not present in static config (e.g. a second
        TurtleBot connecting at runtime)."""
        robot = self._robots.get(robot_id)
        if robot is None:
            robot = RegisteredRobot(robot_id=robot_id, config=config)
            self._robots[robot_id] = robot
        return robot

    def attach_adapter(self, robot_id: str, adapter: RobotAdapter) -> None:
        robot = self._robots[robot_id]
        robot.adapter = adapter

    def mark_connected(self, robot_id: str, registration: RobotRegistration) -> None:
        robot = self._robots[robot_id]
        robot.registration = registration
        robot.connected = True
        robot.last_heartbeat_ms = int(time.time() * 1000)

    def mark_disconnected(self, robot_id: str) -> None:
        robot = self._robots.get(robot_id)
        if robot:
            robot.connected = False

    def mark_stale(self, robot_id: str) -> Optional[RobotAdapter]:
        """Called by the staleness watchdog when a robot stops sending
        telemetry.  Marks disconnected, clears last_state, detaches the
        adapter, and returns it so the caller can await adapter.disconnect()
        to release OS resources (serial port handle, threads)."""
        robot = self._robots.get(robot_id)
        if robot:
            robot.connected = False
            robot.last_state = None
            adapter = robot.adapter
            robot.adapter = None
            return adapter
        return None

    def update_state(self, robot_id: str, state: RobotState) -> None:
        robot = self._robots.get(robot_id)
        if robot is None:
            return
        robot.last_state = state
        robot.last_heartbeat_ms = int(time.time() * 1000)

    def capabilities(self, robot_id: str) -> list[RobotCapability]:
        robot = self._robots.get(robot_id)
        if robot is None or robot.registration is None:
            return []
        return robot.registration.capabilities

    def robot_type(self, robot_id: str) -> Optional[RobotType]:
        robot = self._robots.get(robot_id)
        if robot is None:
            return None
        if robot.registration:
            return robot.registration.robot_type
        try:
            return RobotType(robot.config.type)
        except ValueError:
            return None
