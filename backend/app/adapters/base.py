"""
The adapter contract. Every robot-specific integration (MAVLink, ROS2,
mock, and any future protocol/robot type) implements this interface and
nothing else in the system is allowed to depend on protocol-specific
details — this is the boundary that makes the UI and coordination logic
protocol-agnostic (see docs/architecture.md).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from app.models import RobotCommand, RobotRegistration, RobotState

StateListener = Callable[[RobotState], None]


class RobotAdapter(ABC):
    """One instance per connected robot."""

    robot_id: str

    @abstractmethod
    async def connect(self) -> RobotRegistration:
        """Establish the underlying connection and return this robot's
        registration (capabilities, protocol, etc). Raises on failure —
        callers must not assume partial success."""

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    def get_state(self) -> RobotState:
        """Return the latest normalized RobotState. Must never block on
        network I/O — adapters poll/consume telemetry in the background and
        this just reads the last cached value."""

    @abstractmethod
    async def send_command(self, command: RobotCommand) -> None:
        """Send an already-safety-clamped velocity command. Adapters must
        NOT perform their own clamping beyond a final hardware-limit
        sanity check — clamping is SafetyManager's job, done once,
        upstream of every adapter."""

    def set_state_listener(self, listener: Optional[StateListener]) -> None:
        """Optional: adapters that push state asynchronously (e.g. the
        TurtleBot ingest adapter) call this listener whenever a fresh
        RobotState arrives, so the registry/broadcast loop doesn't need to
        poll faster than the adapter actually updates."""
        self._listener = listener

    def _emit(self, state: RobotState) -> None:
        listener = getattr(self, "_listener", None)
        if listener is not None:
            listener(state)
