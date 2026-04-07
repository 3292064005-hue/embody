from __future__ import annotations

from dataclasses import dataclass

from arm_backend_common.enums import FaultCode, SystemMode


@dataclass
class TransitionResult:
    mode: SystemMode
    reason: str = ""
    fault: FaultCode = FaultCode.NONE
    phase: str = ""


class SystemStateMachine:
    def __init__(self) -> None:
        self.mode = SystemMode.BOOT
        self.phase = "BOOT"
        self.last_reason = "Booting"
        self.last_fault = FaultCode.NONE

    def _set(self, mode: SystemMode, reason: str, fault: FaultCode = FaultCode.NONE, phase: str = "") -> TransitionResult:
        self.mode = mode
        self.last_reason = reason
        self.last_fault = fault
        self.phase = phase or self.phase
        return TransitionResult(mode=mode, reason=reason, fault=fault, phase=self.phase)

    def to_idle(self, reason: str = "System initialized") -> TransitionResult:
        return self._set(SystemMode.IDLE, reason, FaultCode.NONE, "IDLE")

    def start_task(self, reason: str = "Task accepted") -> TransitionResult:
        return self._set(SystemMode.PERCEPTION, reason, FaultCode.NONE, "WAIT_TARGET")

    def perception_ok(self, reason: str = "Valid target acquired") -> TransitionResult:
        return self._set(SystemMode.PLAN, reason, FaultCode.NONE, "TARGET_LOCKED")

    def planning_stage(self, phase: str, reason: str) -> TransitionResult:
        return self._set(SystemMode.PLAN, reason, FaultCode.NONE, phase)

    def plan_ok(self, reason: str = "Motion goal accepted") -> TransitionResult:
        return self._set(SystemMode.EXECUTE, reason, FaultCode.NONE, "EXECUTING")

    def executing_stage(self, phase: str, reason: str) -> TransitionResult:
        return self._set(SystemMode.EXECUTE, reason, FaultCode.NONE, phase)

    def execute_ok(self, reason: str = "Execution finished") -> TransitionResult:
        return self._set(SystemMode.VERIFY, reason, FaultCode.NONE, "VERIFY_RESULT")

    def verify_ok(self, reason: str = "Task completed") -> TransitionResult:
        return self._set(SystemMode.IDLE, reason, FaultCode.NONE, "FINISH")

    def retry_to_perception(self, reason: str) -> TransitionResult:
        return self._set(SystemMode.PERCEPTION, reason, FaultCode.NONE, "WAIT_TARGET")

    def safe_stop(self, reason: str) -> TransitionResult:
        return self._set(SystemMode.SAFE_STOP, reason, self.last_fault, "SAFE_STOP")

    def fault(self, code: FaultCode, reason: str) -> TransitionResult:
        return self._set(SystemMode.FAULT, reason, code, "FAULT")
