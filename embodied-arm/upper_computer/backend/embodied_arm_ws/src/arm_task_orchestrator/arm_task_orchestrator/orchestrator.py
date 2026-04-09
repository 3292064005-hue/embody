from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from arm_backend_common.data_models import CalibrationProfile, HardwareSnapshot, TargetSnapshot, TaskContext, TaskProfile, TaskRequest
from arm_backend_common.enums import FaultCode


@dataclass
class OrchestratorDecision:
    stage: str
    accepted: bool
    message: str
    fault: FaultCode = FaultCode.NONE


class TaskOrchestrator:
    def __init__(self, profile: TaskProfile) -> None:
        self.profile = profile

    def accept_request(self, request: TaskRequest, readiness_ok: bool, readiness_message: str) -> OrchestratorDecision:
        task_type = request.task_type.strip()
        if not task_type:
            return OrchestratorDecision(stage='rejected', accepted=False, message='task type missing', fault=FaultCode.UNKNOWN)
        if request.max_retry < 0:
            return OrchestratorDecision(stage='rejected', accepted=False, message='max_retry must be non-negative', fault=FaultCode.UNKNOWN)
        if not readiness_ok:
            return OrchestratorDecision(stage='rejected', accepted=False, message=readiness_message, fault=FaultCode.UNKNOWN)
        return OrchestratorDecision(stage='queued', accepted=True, message=f'task {request.task_id} accepted')

    def select_target(
        self,
        targets: Iterable[TargetSnapshot],
        selector: str,
        *,
        stale_after_sec: float | None = None,
        now: float | None = None,
        exclude_keys: Iterable[str] | None = None,
    ) -> Optional[TargetSnapshot]:
        excluded = set(exclude_keys or ())
        threshold = self.profile.confidence_threshold
        target_stale_sec = self.profile.stale_target_sec if stale_after_sec is None else stale_after_sec
        matched = [
            item
            for item in targets
            if item.key() not in excluded
            and item.matches_selector(selector)
            and item.confidence >= threshold
            and item.is_fresh(target_stale_sec, now=now)
        ]
        matched.sort(
            key=lambda item: (
                -(item.confidence or 0.0),
                -float(item.received_monotonic or 0.0),
                item.key(),
            )
        )
        return matched[0] if matched else None

    def begin_context(self, request: TaskRequest) -> TaskContext:
        context = TaskContext.from_request(request)
        context.stage = 'perception'
        context.stage_history.append('perception')
        context.last_message = 'waiting_for_target'
        return context

    def verify_hardware_ready(self, hardware: HardwareSnapshot, stale_after_sec: float = 1.2) -> OrchestratorDecision:
        if not hardware.stm32_online:
            return OrchestratorDecision(stage='blocked', accepted=False, message='stm32 offline', fault=FaultCode.SERIAL_DISCONNECTED)
        if hardware.estop_pressed:
            return OrchestratorDecision(stage='blocked', accepted=False, message='estop pressed', fault=FaultCode.ESTOP_TRIGGERED)
        if hardware.limit_triggered:
            return OrchestratorDecision(stage='blocked', accepted=False, message='limit triggered', fault=FaultCode.HARDWARE_LIMIT_TRIGGERED)
        if hardware.hardware_fault_code != 0:
            return OrchestratorDecision(stage='blocked', accepted=False, message='hardware fault present', fault=FaultCode.UNKNOWN)
        if not hardware.is_fresh(stale_after_sec=stale_after_sec):
            return OrchestratorDecision(stage='blocked', accepted=False, message='hardware state stale', fault=FaultCode.SERIAL_DISCONNECTED)
        return OrchestratorDecision(stage='hardware_ready', accepted=True, message='hardware ready')

    def bind_target(self, context: TaskContext, target: TargetSnapshot, calibration: CalibrationProfile) -> TaskContext:
        resolved_place_profile = self.profile.resolve_place_profile(context.target_selector or target.semantic_label, context.place_profile)
        context.place_profile = resolved_place_profile
        context.selected_target = target
        context.target_id = target.target_id
        context.reserved_target_key = target.key()
        context.stage = 'planning'
        if not context.stage_history or context.stage_history[-1] != 'planning':
            context.stage_history.append('planning')
        context.active_place_pose = calibration.resolve_place_profile(resolved_place_profile)
        context.last_message = f'target {target.key()} selected'
        return context

    def decide_retry(self, context: TaskContext, fault: FaultCode, message: str) -> OrchestratorDecision:
        retriable = fault in {FaultCode.TARGET_NOT_FOUND, FaultCode.TARGET_STALE, FaultCode.VISION_TIMEOUT, FaultCode.PLAN_FAILED, FaultCode.EXECUTE_TIMEOUT}
        if context.auto_retry and retriable and context.current_retry < context.max_retry:
            context.current_retry += 1
            context.stage = 'perception'
            context.stage_history.append('retry')
            context.last_message = message
            context.selected_target = None
            context.target_id = None
            context.reserved_target_key = None
            return OrchestratorDecision(stage='retry', accepted=True, message=message, fault=fault)
        context.stage = 'fault'
        context.stage_history.append('fault')
        context.last_message = message
        return OrchestratorDecision(stage='fault', accepted=False, message=message, fault=fault)

    def complete(self, context: TaskContext, message: str = 'task completed') -> OrchestratorDecision:
        context.stage = 'complete'
        context.stage_history.append('complete')
        context.complete_count += 1
        context.last_message = message
        if context.selected_target is not None:
            context.completed_target_ids.add(context.selected_target.key())
        return OrchestratorDecision(stage='complete', accepted=True, message=message)
