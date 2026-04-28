from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arm_backend_common.enums import FaultCode, SystemMode


@dataclass
class SafetyDecision:
    stop_requested: bool
    fault_code: FaultCode = FaultCode.NONE
    severity: str = 'info'
    message: str = ''
    event_type: str = 'SAFE'


class SafetyPolicy:
    ACTIVE_TASK_MODES = {SystemMode.PERCEPTION, SystemMode.PLAN, SystemMode.EXECUTE, SystemMode.VERIFY}

    def evaluate(self, *, system_mode: int | str | None, hardware: dict[str, Any] | None, readiness: dict[str, Any] | None) -> SafetyDecision:
        hardware = hardware or {}
        readiness = readiness or {}
        mode_value = SystemMode(int(system_mode)) if isinstance(system_mode, int) and int(system_mode) in [int(v) for v in SystemMode] else None
        if hardware.get('estop_pressed'):
            return SafetyDecision(True, FaultCode.ESTOP_TRIGGERED, 'critical', 'Emergency stop pressed', 'ESTOP')
        if hardware.get('limit_triggered'):
            return SafetyDecision(True, FaultCode.HARDWARE_LIMIT_TRIGGERED, 'error', 'Workspace or joint limit triggered', 'LIMIT')
        if int(hardware.get('hardware_fault_code', 0) or 0) != 0:
            return SafetyDecision(True, FaultCode.UNKNOWN, 'error', f"Hardware fault {hardware.get('hardware_fault_code')}", 'HARDWARE_FAULT')
        if hardware.get('stale', False):
            return SafetyDecision(True, FaultCode.SERIAL_DISCONNECTED, 'error', 'Hardware state stale', 'HARDWARE_STALE')
        if mode_value in self.ACTIVE_TASK_MODES and readiness:
            if not bool(readiness.get('allReady', False)):
                missing = readiness.get('missingChecks') or []
                detail = ', '.join(str(item) for item in missing) or 'unknown_readiness_loss'
                return SafetyDecision(True, FaultCode.UNKNOWN, 'warn', f'Readiness lost during active task: {detail}', 'READINESS_LOSS')
        return SafetyDecision(False, FaultCode.NONE, 'info', 'safe', 'SAFE')
