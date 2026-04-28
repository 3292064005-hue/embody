from __future__ import annotations

import json
from typing import Any, Callable

from arm_backend_common.enums import FaultCode
from arm_backend_common.event_envelope import encode_event_message
from arm_task_orchestrator.runtime import RuntimeHooks
from arm_common.runtime_messages import build_task_status_message


class TaskNodePublishers:
    """Encapsulate task-orchestrator outbound publishers and summary payloads."""

    def __init__(
        self,
        *,
        string_type,
        fault_report_type,
        task_event_type,
        system_state_type,
        summary_builder,
        mode_to_readiness_mode: dict[Any, str],
        state_pub,
        event_pub,
        fault_pub,
        hardware_cmd_pub,
        summary_pub,
        task_status_pub,
        task_status_typed_pub,
        readiness_pub,
        selected_target_pub,
        plan_request_pub,
        execute_plan_pub,
        now_msg: Callable[[], Any],
    ) -> None:
        self._String = string_type
        self._FaultReport = fault_report_type
        self._TaskEvent = task_event_type
        self._SystemState = system_state_type
        self._summary_builder = summary_builder
        self._mode_to_readiness_mode = dict(mode_to_readiness_mode)
        self._state_pub = state_pub
        self._event_pub = event_pub
        self._fault_pub = fault_pub
        self._hardware_cmd_pub = hardware_cmd_pub
        self._summary_pub = summary_pub
        self._task_status_pub = task_status_pub
        self._task_status_typed_pub = task_status_typed_pub
        self._readiness_pub = readiness_pub
        self._selected_target_pub = selected_target_pub
        self._plan_request_pub = plan_request_pub
        self._execute_plan_pub = execute_plan_pub
        self._now_msg = now_msg

    def build_runtime_hooks(self, emit_event: Callable[..., None], publish_fault: Callable[[FaultCode, str, str], None]) -> RuntimeHooks:
        return RuntimeHooks(
            emit_event=emit_event,
            send_hardware_command=self.send_hardware_command,
            publish_selected_target=self.publish_selected_target,
            publish_fault=publish_fault,
            publish_planning_request=self.publish_planning_request,
            publish_execution_request=self.publish_execution_request,
        )

    def send_hardware_command(self, payload: dict[str, Any]) -> None:
        envelope = dict(payload)
        envelope.setdefault('producer', 'task_orchestrator')
        envelope.setdefault('command_plane', 'task_control')
        self._hardware_cmd_pub.publish(self._String(data=json.dumps(envelope, ensure_ascii=False)))

    def publish_selected_target(self, payload: dict[str, Any]) -> None:
        self._selected_target_pub.publish(self._String(data=json.dumps(payload, ensure_ascii=False)))

    def publish_planning_request(self, payload: dict[str, Any]) -> None:
        self._plan_request_pub.publish(self._String(data=json.dumps(payload, ensure_ascii=False)))

    def publish_execution_request(self, payload: dict[str, Any]) -> None:
        self._execute_plan_pub.publish(self._String(data=json.dumps(payload, ensure_ascii=False)))

    @staticmethod
    def estimate_progress(*, phase: str, awaiting: dict[str, Any] | None, current: Any) -> float:
        mapping = {
            'BOOT': 0.0,
            'IDLE': 0.0,
            'WAIT_TARGET': 15.0,
            'BLOCKED_BY_PERCEPTION': 15.0,
            'TARGET_LOCKED': 40.0,
            'EXECUTING': 72.0,
            'VERIFY_RESULT': 92.0,
            'FINISH': 100.0,
            'SAFE_STOP': 100.0,
            'FAULT': 100.0,
        }
        if current is None and phase == 'FINISH':
            return 100.0
        return float(mapping.get(phase, 50.0 if awaiting else 0.0))

    def publish_system_state(self, *, state_machine, current, hardware, awaiting, calibration, tracker, hardware_fresh_sec: float) -> None:
        msg = self._SystemState()
        msg.header.stamp = self._now_msg()
        msg.system_mode = int(state_machine.mode)
        msg.current_task_id = '' if current is None else current.task_id
        msg.current_stage = state_machine.phase
        msg.hardware_ready = hardware.is_ready(stale_after_sec=hardware_fresh_sec)
        msg.motion_ready = awaiting is None
        msg.calibration_ready = bool(calibration.version) and bool(calibration.active)
        msg.vision_ready = bool(tracker.get_graspable())
        msg.emergency_stop = hardware.estop_pressed
        msg.active_fault_code = int(state_machine.last_fault)
        msg.message = state_machine.last_reason
        self._state_pub.publish(msg)

    def publish_task_status(self, *, current, phase: str, message: str, queue_depth: int, awaiting: dict[str, Any] | None, calibration) -> None:
        payload = self._summary_builder.build_task_status(
            current=current,
            phase=phase,
            message=message,
            queue_depth=queue_depth,
            awaiting=awaiting,
            active_calibration_version=calibration.version,
            active_calibration_workspace=calibration.workspace_id,
            progress=self.estimate_progress(phase=phase, awaiting=awaiting, current=current),
        )
        self._task_status_pub.publish(self._String(data=json.dumps(payload, ensure_ascii=False)))
        if self._task_status_typed_pub is not None:
            self._task_status_typed_pub.publish(build_task_status_message(payload, stamp_factory=self._now_msg))

    def publish_summary(self, *, queue_depth: int, current, phase: str, awaiting: dict[str, Any] | None, tracker, last_feedback: dict[str, Any], mode, action_servers: dict[str, bool]) -> None:
        payload = self._summary_builder.build_runtime_summary(
            queue_depth=queue_depth,
            current=current,
            phase=phase,
            awaiting=awaiting,
            tracker_count=len(tracker.get_graspable()),
            last_feedback=last_feedback,
            mode=self._mode_to_readiness_mode.get(mode, 'task'),
            action_servers=dict(action_servers),
        )
        self._summary_pub.publish(self._String(data=json.dumps(payload, ensure_ascii=False)))

    def publish_readiness(self, *, state_machine, supports_action_goals: bool) -> None:
        runtime_phase = self._summary_builder.runtime_phase_from_phase(state_machine.phase)
        task_stage = self._summary_builder.task_stage_from_phase(state_machine.phase)
        controller_mode = self._summary_builder.controller_mode_from_runtime_phase(runtime_phase)
        readiness_mode = self._mode_to_readiness_mode.get(state_machine.mode, 'task')
        blocked = str(state_machine.phase or '').upper() == 'BLOCKED_BY_PERCEPTION'
        ok = str(state_machine.phase or '').upper() not in {'FAULT', 'SAFE_STOP', 'BLOCKED_BY_PERCEPTION'}
        self._readiness_pub.publish(self._String(data=json.dumps({
            'check': 'task_orchestrator',
            'ok': ok,
            'detail': state_machine.phase.lower(),
            'mode': readiness_mode,
            'controllerMode': controller_mode,
            'runtimePhase': runtime_phase,
            'taskStage': task_stage,
            'blocked': blocked,
            'blockingReason': state_machine.last_reason if blocked else '',
            'staleAfterSec': 2.0,
            'supportsActionGoals': supports_action_goals,
        }, ensure_ascii=False)))

    def publish_fault_report(self, *, code: FaultCode, task_id: str, message: str) -> None:
        fault = self._FaultReport()
        fault.stamp = self._now_msg()
        fault.code = int(code)
        fault.source = 'task_orchestrator'
        fault.severity = 'error'
        fault.task_id = task_id
        fault.message = encode_event_message(message, stage='fault', error_code=str(code.name).lower(), operator_actionable=True)
        self._fault_pub.publish(fault)

    def emit_event(self, *, level: str, source: str, event_type: str, task_id: str, code: int, message: str, current, phase: str, stage: str | None = None, error_code: str | None = None, operator_actionable: bool | None = None, payload: dict[str, Any] | None = None) -> None:
        msg = self._TaskEvent()
        msg.stamp = self._now_msg()
        msg.level = level
        msg.source = source
        msg.event_type = event_type
        msg.task_id = task_id
        msg.code = int(code)
        msg.message = encode_event_message(
            message,
            request_id=getattr(current, 'request_id', None),
            correlation_id=getattr(current, 'correlation_id', None),
            task_run_id=getattr(current, 'task_run_id', None),
            episode_id=getattr(current, 'episode_id', None),
            stage=stage or (getattr(current, 'stage', '') or phase.lower()),
            error_code=error_code,
            operator_actionable=operator_actionable,
            payload=payload,
        )
        self._event_pub.publish(msg)
