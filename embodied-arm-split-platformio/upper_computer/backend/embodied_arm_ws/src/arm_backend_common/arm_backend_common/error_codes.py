from .enums import FaultCode

FAULT_MESSAGES = {
    FaultCode.NONE: "No fault",
    FaultCode.VISION_TIMEOUT: "Vision target acquisition timed out",
    FaultCode.TARGET_NOT_FOUND: "No valid target found in workspace",
    FaultCode.TARGET_STALE: "Target information became stale before execution",
    FaultCode.PLAN_FAILED: "Motion planning failed",
    FaultCode.MOTION_SERVER_UNAVAILABLE: "Motion action server unavailable",
    FaultCode.EXECUTE_TIMEOUT: "Motion execution timed out",
    FaultCode.EXECUTE_CANCELED: "Motion execution canceled",
    FaultCode.SERIAL_DISCONNECTED: "STM32 serial link disconnected",
    FaultCode.HARDWARE_LIMIT_TRIGGERED: "Hardware limit was triggered",
    FaultCode.GRIPPER_FAILURE: "Gripper confirmation failed",
    FaultCode.ESTOP_TRIGGERED: "Emergency stop was triggered",
    FaultCode.HARDWARE_NACK: "Hardware command was rejected",
    FaultCode.UNKNOWN: "Unknown system fault",
}


def fault_message(code: int) -> str:
    try:
        enum_code = FaultCode(code)
    except ValueError:
        return FAULT_MESSAGES[FaultCode.UNKNOWN]
    return FAULT_MESSAGES.get(enum_code, FAULT_MESSAGES[FaultCode.UNKNOWN])
