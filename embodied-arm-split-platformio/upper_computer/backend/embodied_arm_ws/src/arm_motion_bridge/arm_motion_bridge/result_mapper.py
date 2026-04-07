from __future__ import annotations

from arm_backend_common.enums import FaultCode


def map_stage_failure(reason: str) -> FaultCode:
    reason_norm = reason.lower()
    if "nack" in reason_norm:
        return FaultCode.HARDWARE_NACK
    if "fault" in reason_norm:
        return FaultCode.UNKNOWN
    if "cancel" in reason_norm:
        return FaultCode.EXECUTE_CANCELED
    if "unavailable" in reason_norm:
        return FaultCode.MOTION_SERVER_UNAVAILABLE
    return FaultCode.EXECUTE_TIMEOUT
