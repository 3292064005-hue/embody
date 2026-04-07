from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from arm_grasp_planner import GraspPlannerNode
from arm_scene_manager import SceneManagerNode


@runtime_checkable
class SceneSnapshotProvider(Protocol):
    """Port used by :class:`MotionPlanner` to obtain scene snapshots."""

    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply a scene-sync payload and return the updated snapshot."""


@runtime_checkable
class GraspPlanProvider(Protocol):
    """Port used by :class:`MotionPlanner` to obtain grasp plans."""

    def plan(
        self,
        target: dict[str, Any],
        place_zone: dict[str, Any] | None = None,
        *,
        failed_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a serialized grasp plan for a target and place zone."""


class SceneManagerAdapter:
    """Default adapter that exposes ``SceneManagerNode`` through the scene port."""

    def __init__(self, node: SceneManagerNode | None = None) -> None:
        self._node = node or SceneManagerNode(enable_ros_io=False)

    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._node.sync_scene(payload)


class GraspPlannerAdapter:
    """Default adapter that exposes ``GraspPlannerNode`` through the grasp port."""

    def __init__(self, node: GraspPlannerNode | None = None) -> None:
        self._node = node or GraspPlannerNode(enable_ros_io=False)

    def plan(
        self,
        target: dict[str, Any],
        place_zone: dict[str, Any] | None = None,
        *,
        failed_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._node.plan(target, place_zone, failed_ids=failed_ids)
