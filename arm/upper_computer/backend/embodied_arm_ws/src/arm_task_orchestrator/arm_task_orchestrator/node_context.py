from __future__ import annotations

"""Node wiring helpers for the task orchestrator."""

from arm_task_orchestrator.runtime import RuntimeHooks
from arm_task_orchestrator.stack_factory import build_runtime_engine


def build_runtime_hooks(*, publishers, emit_event, publish_fault) -> RuntimeHooks:
    """Build runtime hooks for the task-orchestrator node."""
    return publishers.build_runtime_hooks(emit_event=emit_event, publish_fault=publish_fault)


def build_runtime_stack(*, state_machine, application, execution_adapter, fault_manager, tracker, state, publishers, emit_event, publish_fault):
    """Build the runtime engine and hook bundle used by the orchestrator node."""
    hooks = build_runtime_hooks(publishers=publishers, emit_event=emit_event, publish_fault=publish_fault)
    runtime_engine = build_runtime_engine(
        state_machine=state_machine,
        application=application,
        execution_adapter=execution_adapter,
        fault_manager=fault_manager,
        tracker=tracker,
        state=state,
        hooks=hooks,
    )
    return runtime_engine, hooks
