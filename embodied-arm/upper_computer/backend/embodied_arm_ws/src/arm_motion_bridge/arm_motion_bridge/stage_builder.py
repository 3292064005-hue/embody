from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from arm_backend_common.data_models import CalibrationProfile


@dataclass
class MotionStage:
    stage: str
    kind: str
    timeout_sec: float
    x: float | None = None
    y: float | None = None
    z: float | None = None
    yaw: float | None = None
    cancel_behavior: str = "stop"
    retryable: bool = True

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "stage": self.stage,
            "kind": self.kind,
            "timeout_sec": self.timeout_sec,
            "cancel_behavior": self.cancel_behavior,
            "retryable": self.retryable,
        }
        for key in ("x", "y", "z", "yaw"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload


class StageBuilder:
    def __init__(self, calibration: CalibrationProfile) -> None:
        self.calibration = calibration

    def build_pick_and_place(self, x: float, y: float, yaw: float, place_profile: str) -> List[MotionStage]:
        place = self.calibration.resolve_place_profile(place_profile)
        retreat_z = max(self.calibration.retreat_z, self.calibration.place_z + 0.05)
        return [
            MotionStage("PRE_GRASP", "EXEC_STAGE", timeout_sec=1.2, x=x, y=y, z=self.calibration.pre_grasp_z, yaw=yaw),
            MotionStage("DESCEND", "EXEC_STAGE", timeout_sec=1.2, x=x, y=y, z=self.calibration.grasp_z, yaw=yaw),
            MotionStage("CLOSE_GRIPPER", "CLOSE_GRIPPER", timeout_sec=0.8, retryable=False),
            MotionStage("LIFT", "EXEC_STAGE", timeout_sec=1.0, x=x, y=y, z=self.calibration.pre_grasp_z, yaw=yaw),
            MotionStage("MOVE_TO_PLACE", "EXEC_STAGE", timeout_sec=1.4, x=place["x"], y=place["y"], z=self.calibration.place_z, yaw=place["yaw"]),
            MotionStage("OPEN_GRIPPER", "OPEN_GRIPPER", timeout_sec=0.8, retryable=False),
            MotionStage("RETREAT", "EXEC_STAGE", timeout_sec=1.0, x=place["x"], y=place["y"], z=retreat_z, yaw=place["yaw"]),
            MotionStage("GO_HOME", "HOME", timeout_sec=1.6, retryable=False),
        ]
