from __future__ import annotations

"""Coordinator layer for task-orchestrator runtime ticking and transitions."""

from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeCoordinator:
    """Thin coordinator that centralizes runtime-engine interactions.

    Args:
        runtime_engine: Split-stack runtime engine.
        state_machine: Public state machine facade.
        emit_event: Callback used for operator-visible event emission.

    Returns:
        None.

    Raises:
        Does not raise during construction.
    """

    runtime_engine: Any
    state_machine: Any
    emit_event: Any

    def enqueue_task(self, request: Any, *, hardware_fresh_sec: float) -> Any:
        return self.runtime_engine.enqueue_task_request(request, hardware_fresh_sec=hardware_fresh_sec)

    def mark_task_terminal(self, task_id: str, *, state: str, result_code: int, message: str, elapsed: float | None = None) -> None:
        self.runtime_engine.mark_task_terminal(task_id, state=state, result_code=result_code, message=message, elapsed=elapsed)

    def cancel_task_by_id(self, task_id: str, reason: str) -> None:
        self.runtime_engine.cancel_task_by_id(task_id, reason)

    def elapsed_for_task(self, task_id: str) -> float:
        return self.runtime_engine.elapsed_for_task(task_id)

    def update_target(self, target: Any) -> None:
        self.runtime_engine.update_target(target)

    def update_plan_result(self, payload: dict[str, Any]) -> None:
        self.runtime_engine.update_plan_result(payload)

    def update_execution_status(self, payload: dict[str, Any]) -> None:
        self.runtime_engine.update_execution_status(payload)
