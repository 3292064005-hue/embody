from __future__ import annotations

from arm_backend_common.data_models import TaskProfile
from arm_task_orchestrator.application_service import TaskApplicationService
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultManager
from arm_task_orchestrator.orchestrator import TaskOrchestrator
from arm_task_orchestrator.runtime import RuntimeHooks, TaskRuntimeEngine, TaskRuntimeState
from arm_task_orchestrator.state_machine import SystemStateMachine
from arm_task_orchestrator.verification import VerificationManager
from arm_perception import VisionTargetTracker


def build_target_tracker(task_profile: TaskProfile, *, stable_seen_count: int) -> VisionTargetTracker:
    """Create the runtime vision tracker from task-profile thresholds.

    Args:
        task_profile: Task profile containing stale-target timing constraints.
        stable_seen_count: Minimum stable detections required before a target is treated as valid.

    Returns:
        A configured `VisionTargetTracker` instance.

    Raises:
        ValueError: Propagated if downstream tracker construction rejects invalid numeric values.

    Boundary behavior:
        Stable detection count is clamped to at least one observation.
    """
    return VisionTargetTracker(
        stale_after_sec=task_profile.stale_target_sec,
        min_seen_count=max(1, int(stable_seen_count)),
    )


def build_application_service(
    task_profile: TaskProfile,
    execution_adapter: ExecutionAdapter,
    verification: VerificationManager,
    fault_manager: FaultManager,
) -> tuple[TaskOrchestrator, TaskApplicationService]:
    """Build the orchestrator/application pair used by the task runtime.

    Args:
        task_profile: Active task profile driving orchestration policy.
        execution_adapter: Adapter that forwards high-level task intents to execution transport.
        verification: Verification manager for calibration and precondition checks.
        fault_manager: Fault manager coordinating latching and recovery policies.

    Returns:
        A `(TaskOrchestrator, TaskApplicationService)` tuple wired to the supplied dependencies.

    Raises:
        ValueError: Propagated if downstream constructors reject invalid task-profile data.

    Boundary behavior:
        The application service is created with a deferred runtime engine reference that is bound later.
    """
    orchestrator = TaskOrchestrator(task_profile)
    application = TaskApplicationService(
        orchestrator,
        None,
        execution_adapter,
        verification,
        fault_manager,
        task_profile,
    )
    return orchestrator, application


def build_runtime_engine(
    *,
    state_machine: SystemStateMachine,
    application: TaskApplicationService,
    execution_adapter: ExecutionAdapter,
    fault_manager: FaultManager,
    tracker: VisionTargetTracker,
    state: TaskRuntimeState,
    hooks: RuntimeHooks,
) -> TaskRuntimeEngine:
    """Assemble the runtime engine that coordinates task-state execution.

    Args:
        state_machine: State machine governing operator-visible task transitions.
        application: Application service handling task orchestration rules.
        execution_adapter: Adapter bridging runtime decisions into motion execution calls.
        fault_manager: Fault manager tracking latches and recovery transitions.
        tracker: Vision tracker used to stabilize perception targets.
        state: Mutable runtime state snapshot.
        hooks: Runtime hooks for telemetry and gateway-facing side effects.

    Returns:
        A fully configured `TaskRuntimeEngine`.

    Raises:
        ValueError: Propagated if engine construction receives invalid dependencies.

    Boundary behavior:
        No ROS side effects are triggered during construction; wiring is purely in-memory.
    """
    return TaskRuntimeEngine(
        state_machine=state_machine,
        application=application,
        execution_adapter=execution_adapter,
        fault_manager=fault_manager,
        tracker=tracker,
        state=state,
        hooks=hooks,
    )
