from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from arm_backend_common.data_models import CalibrationProfile


@dataclass
class CalibrationModel:
    profile: CalibrationProfile = field(default_factory=CalibrationProfile)

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "CalibrationModel":
        compensation = cfg.get("compensation", {}) or {}
        top_level_comp = {k: cfg.get(k) for k in ("x_bias", "y_bias", "yaw_bias") if cfg.get(k) is not None}
        compensation = {**top_level_comp, **compensation}
        robot = cfg.get("robot", {})
        placement = cfg.get("placement", {})
        metadata = cfg.get("metadata", {}) or {}
        profile = CalibrationProfile(
            version=str(cfg.get("version", "default")),
            x_bias=float(compensation.get("x_bias", 0.0)),
            y_bias=float(compensation.get("y_bias", 0.0)),
            yaw_bias=float(compensation.get("yaw_bias", 0.0)),
            pre_grasp_z=float(robot.get("pre_grasp_z", 0.12)),
            grasp_z=float(robot.get("grasp_z", 0.03)),
            place_z=float(robot.get("place_z", 0.05)),
            retreat_z=float(robot.get("retreat_z", robot.get("pre_grasp_z", 0.12))),
            place_profiles=dict(placement.get("profiles", {})),
            created_at=str(metadata.get("created_at", cfg.get("created_at", ""))),
            operator=str(metadata.get("operator", cfg.get("operator", ""))),
            camera_serial=str(metadata.get("camera_serial", cfg.get("camera_serial", ""))),
            robot_description_hash=str(metadata.get("robot_description_hash", cfg.get("robot_description_hash", ""))),
            workspace_id=str(metadata.get("workspace_id", cfg.get("workspace_id", "default"))),
            active=bool(metadata.get("active", cfg.get("active", True))),
        )
        return cls(profile=profile)


    @property
    def x_bias(self) -> float:
        return float(self.profile.x_bias)

    @property
    def y_bias(self) -> float:
        return float(self.profile.y_bias)

    @property
    def yaw_bias(self) -> float:
        return float(self.profile.yaw_bias)

    def table_to_robot(self, x: float, y: float, yaw: float) -> tuple[float, float, float]:
        return self.profile.apply_target(x, y, yaw)

    def to_dict(self) -> Dict[str, Any]:
        return self.profile.to_dict()
