from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class HardwareSemanticState:
    estop_pressed: bool = False
    home_ok: bool = False
    gripper_ok: bool = False
    gripper_open: bool = True
    motion_busy: bool = False
    limit_triggered: bool = False
    joint_position: List[float] = field(default_factory=list)
    joint_velocity: List[float] = field(default_factory=list)
    hardware_fault_code: int = 0
    last_kind: str = ""
    last_stage: str = ""
    last_result: str = ""
    transport_state: str = "idle"
    transport_result: str = "idle"
    actuation_state: str = "idle"
    actuation_result: str = "idle"
    execution_state: str = "idle"
    result_code: str = "idle"
    last_sequence: int = -1
    task_id: str = ""

    def apply_report(self, payload: Dict[str, Any]) -> None:
        self.estop_pressed = bool(payload.get("estop_pressed", self.estop_pressed))
        self.home_ok = bool(payload.get("home_ok", self.home_ok))
        self.gripper_ok = bool(payload.get("gripper_ok", self.gripper_ok))
        self.gripper_open = bool(payload.get("gripper_open", self.gripper_open))
        self.motion_busy = bool(payload.get("motion_busy", self.motion_busy))
        self.limit_triggered = bool(payload.get("limit_triggered", self.limit_triggered))
        self.joint_position = [float(v) for v in payload.get("joint_position", self.joint_position)]
        self.joint_velocity = [float(v) for v in payload.get("joint_velocity", self.joint_velocity)]
        self.hardware_fault_code = int(payload.get("hardware_fault_code", self.hardware_fault_code))
        self.last_kind = str(payload.get("last_kind", self.last_kind))
        self.last_stage = str(payload.get("last_stage", self.last_stage))
        self.last_result = str(payload.get("last_result", self.last_result))
        self.transport_state = str(payload.get("transport_state", self.transport_state))
        self.transport_result = str(payload.get("transport_result", self.transport_result))
        self.actuation_state = str(payload.get("actuation_state", payload.get("execution_state", self.actuation_state)))
        self.actuation_result = str(payload.get("actuation_result", payload.get("result_code", payload.get("last_result", self.actuation_result))))
        self.execution_state = str(payload.get("execution_state", self.execution_state))
        self.result_code = str(payload.get("result_code", self.result_code))
        self.last_sequence = int(payload.get("last_sequence", self.last_sequence))
        self.task_id = str(payload.get("task_id", self.task_id))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estop_pressed": self.estop_pressed,
            "home_ok": self.home_ok,
            "gripper_ok": self.gripper_ok,
            "gripper_open": self.gripper_open,
            "motion_busy": self.motion_busy,
            "limit_triggered": self.limit_triggered,
            "joint_position": self.joint_position,
            "joint_velocity": self.joint_velocity,
            "hardware_fault_code": self.hardware_fault_code,
            "last_kind": self.last_kind,
            "last_stage": self.last_stage,
            "last_result": self.last_result,
            "transport_state": self.transport_state,
            "transport_result": self.transport_result,
            "actuation_state": self.actuation_state,
            "actuation_result": self.actuation_result,
            "execution_state": self.execution_state,
            "result_code": self.result_code,
            "last_sequence": self.last_sequence,
            "task_id": self.task_id,
        }
