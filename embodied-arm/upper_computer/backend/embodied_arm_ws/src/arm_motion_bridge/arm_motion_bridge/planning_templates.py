from __future__ import annotations

from typing import Dict, List

from arm_backend_common.data_models import CalibrationProfile


StageDict = Dict[str, float | str | bool]


def build_pick_sequence(x: float, y: float, yaw: float, calibration: CalibrationProfile) -> List[StageDict]:
    return [
        {"stage": "PRE_GRASP", "kind": "EXEC_STAGE", "x": x, "y": y, "z": calibration.pre_grasp_z, "yaw": yaw, "timeout_sec": 1.2},
        {"stage": "DESCEND", "kind": "EXEC_STAGE", "x": x, "y": y, "z": calibration.grasp_z, "yaw": yaw, "timeout_sec": 1.2},
        {"stage": "CLOSE_GRIPPER", "kind": "CLOSE_GRIPPER", "timeout_sec": 0.8},
        {"stage": "LIFT", "kind": "EXEC_STAGE", "x": x, "y": y, "z": calibration.pre_grasp_z, "yaw": yaw, "timeout_sec": 1.0},
    ]


def build_place_sequence(place_profile: str, calibration: CalibrationProfile) -> List[StageDict]:
    p = calibration.resolve_place_profile(place_profile)
    retreat_z = max(calibration.retreat_z, calibration.place_z + 0.05)
    return [
        {"stage": "MOVE_TO_PLACE", "kind": "EXEC_STAGE", "x": p["x"], "y": p["y"], "z": calibration.place_z, "yaw": p["yaw"], "timeout_sec": 1.4},
        {"stage": "OPEN_GRIPPER", "kind": "OPEN_GRIPPER", "timeout_sec": 0.8},
        {"stage": "RETREAT", "kind": "EXEC_STAGE", "x": p["x"], "y": p["y"], "z": retreat_z, "yaw": p["yaw"], "timeout_sec": 1.0},
        {"stage": "GO_HOME", "kind": "HOME", "timeout_sec": 1.6},
    ]
