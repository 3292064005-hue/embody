from __future__ import annotations

from dataclasses import dataclass

from arm_backend_common.enums import FaultCode


@dataclass
class RecoveryDecision:
    message: str
    publish_stop: bool = True
    publish_home: bool = False
    replan: bool = False
    reacquire_target: bool = False


class RecoveryManager:
    def decide(self, code: FaultCode, detail: str) -> RecoveryDecision:
        if code in {FaultCode.TARGET_STALE, FaultCode.TARGET_NOT_FOUND, FaultCode.VISION_TIMEOUT}:
            return RecoveryDecision(message=detail, publish_stop=False, publish_home=False, reacquire_target=True)
        if code in {FaultCode.PLAN_FAILED, FaultCode.MOTION_SERVER_UNAVAILABLE}:
            return RecoveryDecision(message=detail, publish_stop=True, publish_home=False, replan=True)
        if code in {FaultCode.EXECUTE_TIMEOUT, FaultCode.HARDWARE_NACK, FaultCode.GRIPPER_FAILURE}:
            return RecoveryDecision(message=detail, publish_stop=True, publish_home=True)
        if code in {FaultCode.ESTOP_TRIGGERED, FaultCode.HARDWARE_LIMIT_TRIGGERED, FaultCode.SERIAL_DISCONNECTED}:
            return RecoveryDecision(message=detail, publish_stop=True, publish_home=False)
        return RecoveryDecision(message=detail, publish_stop=True, publish_home=False)
