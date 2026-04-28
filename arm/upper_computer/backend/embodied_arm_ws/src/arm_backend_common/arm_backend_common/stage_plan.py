from __future__ import annotations

"""Shared stage-plan contracts for planner/executor split-stack coordination."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StagePlan:
    """Serializable stage-plan record shared across planner, executor, and runtime contracts.

    Args:
        name: Stable stage identifier.
        kind: Stage category such as connector, propagator, or gripper.
        payload: Serializable stage payload.

    Returns:
        None.

    Raises:
        Does not raise during initialization.

    Boundary behavior:
        ``payload`` is copied to a plain dictionary by callers before serialization
        so runtime transports never depend on mutable external references.
    """

    name: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
