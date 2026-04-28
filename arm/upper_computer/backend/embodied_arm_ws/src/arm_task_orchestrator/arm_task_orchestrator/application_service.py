from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TargetSnapshot, TaskContext, TaskRequest, TaskProfile
from arm_backend_common.enums import FaultCode
from arm_task_orchestrator.execution_adapter import ExecutionAdapter
from arm_task_orchestrator.fault_manager import FaultDecision, FaultManager
from arm_task_orchestrator.orchestrator import OrchestratorDecision, TaskOrchestrator
from arm_task_orchestrator.planning_adapter import PlanningAdapter, PlanningResult
from arm_task_orchestrator.verification import VerificationManager, VerificationResult


@dataclass
class VerificationDecision:
    finished: bool
    success: bool
    message: str
    fault: FaultCode = FaultCode.NONE


class TaskApplicationService:
    """Pure application-layer orchestration helpers for the task node."""

    def __init__(
        self,
        orchestrator: TaskOrchestrator,
        planning_adapter: PlanningAdapter | None,
        execution_adapter: ExecutionAdapter,
        verification: VerificationManager,
        fault_manager: FaultManager,
        profile: TaskProfile,
        *,
        allow_legacy_in_process_planning: bool = False,
    ) -> None:
        self._orchestrator = orchestrator
        self._planning = planning_adapter
        self._execution = execution_adapter
        self._verification = verification
        self._faults = fault_manager
        self._profile = profile
        self._allow_legacy_in_process_planning = bool(allow_legacy_in_process_planning)

    @property
    def execution(self) -> ExecutionAdapter:
        return self._execution

    def begin_task(self, request: TaskRequest) -> TaskContext:
        return self._orchestrator.begin_context(request)

    def accept_request(self, request: TaskRequest, readiness_ok: bool, readiness_message: str) -> OrchestratorDecision:
        return self._orchestrator.accept_request(request, readiness_ok, readiness_message)

    def select_target(self, targets: Iterable[TargetSnapshot], selector: str, *, exclude_keys: Iterable[str] | None = None) -> TargetSnapshot | None:
        return self._orchestrator.select_target(targets, selector, exclude_keys=exclude_keys)

    def bind_target(self, context: TaskContext, target: TargetSnapshot, calibration: CalibrationProfile) -> TaskContext:
        """Bind the selected target and calibration without performing planning.

        Args:
            context: Active task context.
            target: Selected target snapshot.
            calibration: Active calibration profile.

        Returns:
            TaskContext: Updated task context.
        """
        return self._orchestrator.bind_target(context, target, calibration)

    def bind_and_plan(self, context: TaskContext, target: TargetSnapshot, calibration: CalibrationProfile) -> PlanningResult:
        """Compatibility-only helper for legacy in-process planning tests.

        Args:
            context: Active task context.
            target: Selected target snapshot.
            calibration: Active calibration profile.

        Returns:
            PlanningResult: In-process execution bundle built by the legacy planning adapter.

        Raises:
            RuntimeError: Raised when the active stack does not explicitly opt into
                the compatibility path, or when no planning adapter is available.

        Boundary behavior:
            Active runtime stacks remain split-stack only. Callers must opt into
            the compatibility path explicitly so this helper cannot silently become
            a second production planning lane.
        """
        self._orchestrator.bind_target(context, target, calibration)
        if not self._allow_legacy_in_process_planning:
            raise RuntimeError('legacy in-process planning is disabled; active runtime stacks must use split-stack request/result planning')
        if self._planning is None:
            raise RuntimeError('planning adapter unavailable for legacy in-process planning')
        return self._planning.build_execution_bundle(context, target, calibration)

    def verify_outcome(self, context: TaskContext, hardware: HardwareSnapshot, latest_target: TargetSnapshot | None, now: float) -> VerificationDecision:
        result: VerificationResult = self._verification.verify(context, self._profile, hardware, latest_target, now)
        if not result.finished:
            return VerificationDecision(False, False, result.message)
        if result.success:
            return VerificationDecision(True, True, result.message)
        decision: OrchestratorDecision = self._orchestrator.decide_retry(context, FaultCode.TARGET_STALE, result.message)
        if decision.accepted:
            return VerificationDecision(True, False, decision.message, decision.fault)
        fault: FaultDecision = self._faults.classify(decision.fault, decision.message)
        return VerificationDecision(True, False, fault.reason, fault.fault)

    def complete(self, context: TaskContext, message: str) -> OrchestratorDecision:
        return self._orchestrator.complete(context, message)
