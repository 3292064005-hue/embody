from __future__ import annotations


class MotionPlannerError(RuntimeError):
    """Base exception for motion planner failures."""


class InvalidTargetError(MotionPlannerError, ValueError):
    """Raised when a selected target is missing required or valid fields."""


class WorkspaceViolationError(MotionPlannerError, ValueError):
    """Raised when a target or place pose leaves the configured workspace."""


class SceneUnavailableError(MotionPlannerError):
    """Raised when the planning scene cannot be queried or is unavailable."""


class PlanningUnavailableError(MotionPlannerError):
    """Raised when no planning backend is available to accept a request."""


class PlanningFailedError(MotionPlannerError):
    """Raised when the planning backend rejects a valid request."""
