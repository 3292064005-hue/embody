from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Any

import yaml


class SafetyViolation(ValueError):
    """Raised when a runtime command violates configured safety limits."""


@dataclass(frozen=True)
class JointLimit:
    has_position_limits: bool
    min_position: float
    max_position: float

    def contains(self, value: float) -> bool:
        if not self.has_position_limits:
            return True
        return self.min_position <= float(value) <= self.max_position


@dataclass(frozen=True)
class ManualCommandLimits:
    max_servo_cartesian_delta: float
    max_jog_joint_step_deg: float


@dataclass(frozen=True)
class SafetyLimits:
    source_path: str
    joint_limits: dict[str, JointLimit]
    max_cartesian_speed_mps: float
    max_cartesian_accel_mps2: float
    max_gripper_force: float
    manual_command_limits: ManualCommandLimits

    def joint_name_for_index(self, joint_index: int) -> str:
        return f'joint_{int(joint_index) + 1}'

    def require_joint_positions(self, joint_names: list[str], positions: list[float], *, context: str) -> None:
        if len(joint_names) != len(positions):
            raise SafetyViolation(f'{context}: joint_names and positions length mismatch')
        for joint_name, position in zip(joint_names, positions):
            name = str(joint_name).strip()
            if not name:
                raise SafetyViolation(f'{context}: joint name must be non-empty')
            if not isfinite(float(position)):
                raise SafetyViolation(f'{context}: joint {name} position must be finite')
            limit = self.joint_limits.get(name)
            if limit is None:
                raise SafetyViolation(f'{context}: safety limits missing joint {name}')
            if not limit.contains(float(position)):
                raise SafetyViolation(
                    f'{context}: joint {name} target {float(position):.6f} outside '
                    f'[{limit.min_position:.6f}, {limit.max_position:.6f}]'
                )

    def require_execution_target(self, target: dict[str, Any], *, context: str) -> None:
        if not isinstance(target, dict):
            raise SafetyViolation(f'{context}: execution_target must be a dictionary')
        joint_names = [str(item) for item in list(target.get('joint_names') or [])]
        if not joint_names:
            raise SafetyViolation(f'{context}: execution_target joint_names must be provided')
        points = list(target.get('points') or [])
        if not points:
            raise SafetyViolation(f'{context}: execution_target points must be provided')
        for index, point in enumerate(points, start=1):
            if not isinstance(point, dict):
                raise SafetyViolation(f'{context}: execution_target point {index} must be a dictionary')
            positions = [float(item) for item in list(point.get('positions') or [])]
            if not positions:
                raise SafetyViolation(f'{context}: execution_target point {index} positions must be provided')
            self.require_joint_positions(joint_names, positions, context=f'{context} point {index}')
            accelerations = point.get('accelerations')
            if accelerations is not None:
                values = [float(item) for item in list(accelerations or [])]
                if any(not isfinite(value) or value < 0.0 for value in values):
                    raise SafetyViolation(f'{context}: execution_target point {index} accelerations must be finite and non-negative')
            time_from_start = float(point.get('time_from_start_sec', 0.0) or 0.0)
            if time_from_start <= 0.0 or not isfinite(time_from_start):
                raise SafetyViolation(f'{context}: execution_target point {index} time_from_start_sec must be positive and finite')

    def require_gripper_force(self, force: float, *, context: str) -> None:
        value = float(force)
        if not isfinite(value):
            raise SafetyViolation(f'{context}: gripper force must be finite')
        if value < 0.0 or value > self.max_gripper_force:
            raise SafetyViolation(f'{context}: gripper force {value:.6f} exceeds configured max {self.max_gripper_force:.6f}')

    def require_manual_servo(self, *, axis: str, delta: float, context: str) -> None:
        normalized_axis = str(axis).strip()
        if normalized_axis not in {'x', 'y', 'z', 'rx', 'ry', 'rz'}:
            raise SafetyViolation(f'{context}: unsupported servo axis {normalized_axis or "<empty>"}')
        value = float(delta)
        if not isfinite(value) or value == 0.0:
            raise SafetyViolation(f'{context}: servo delta must be finite and non-zero')
        limit = self.manual_command_limits.max_servo_cartesian_delta
        if abs(value) > limit:
            raise SafetyViolation(f'{context}: servo delta {value:.6f} exceeds configured max {limit:.6f}')

    def require_manual_jog(self, *, joint_index: int, direction: int, step_deg: float, context: str) -> None:
        joint_name = self.joint_name_for_index(int(joint_index))
        if joint_name not in self.joint_limits:
            raise SafetyViolation(f'{context}: jointIndex {joint_index} out of range')
        if int(direction) not in {-1, 1}:
            raise SafetyViolation(f'{context}: direction must be -1 or 1')
        value = float(step_deg)
        if not isfinite(value) or value <= 0.0:
            raise SafetyViolation(f'{context}: stepDeg must be finite and positive')
        limit = self.manual_command_limits.max_jog_joint_step_deg
        if value > limit:
            raise SafetyViolation(f'{context}: stepDeg {value:.6f} exceeds configured max {limit:.6f}')


def _default_safety_limits_path() -> Path:
    return Path(__file__).resolve().parents[2] / 'arm_bringup' / 'config' / 'safety_limits.yaml'


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(payload, dict):
        raise ValueError(f'safety limits root must be a mapping: {path}')
    return payload


def _normalize_joint_limits(payload: dict[str, Any], *, source: Path) -> dict[str, JointLimit]:
    joints = payload.get('joint_limits', {})
    if not isinstance(joints, dict) or not joints:
        raise ValueError(f'safety limits missing joint_limits: {source}')
    result: dict[str, JointLimit] = {}
    for name, value in joints.items():
        if not isinstance(value, dict):
            raise ValueError(f'safety limits joint entry must be a mapping: {source}::{name}')
        result[str(name)] = JointLimit(
            has_position_limits=bool(value.get('has_position_limits', False)),
            min_position=float(value.get('min_position', 0.0)),
            max_position=float(value.get('max_position', 0.0)),
        )
    return result


@lru_cache(maxsize=8)
def load_safety_limits(path: str | Path | None = None) -> SafetyLimits:
    source = Path(path).expanduser().resolve() if path else _default_safety_limits_path().resolve()
    payload = _load_yaml(source)
    manual_payload = payload.get('manual_command_limits', {}) if isinstance(payload.get('manual_command_limits'), dict) else {}
    limits = SafetyLimits(
        source_path=str(source),
        joint_limits=_normalize_joint_limits(payload, source=source),
        max_cartesian_speed_mps=float(payload.get('max_cartesian_speed_mps', 0.15)),
        max_cartesian_accel_mps2=float(payload.get('max_cartesian_accel_mps2', 0.4)),
        max_gripper_force=float(payload.get('max_gripper_force', 0.4)),
        manual_command_limits=ManualCommandLimits(
            max_servo_cartesian_delta=float(manual_payload.get('max_servo_cartesian_delta', 0.1)),
            max_jog_joint_step_deg=float(manual_payload.get('max_jog_joint_step_deg', 10.0)),
        ),
    )
    if limits.manual_command_limits.max_servo_cartesian_delta <= 0.0:
        raise ValueError(f'safety limits max_servo_cartesian_delta must be positive: {source}')
    if limits.manual_command_limits.max_jog_joint_step_deg <= 0.0:
        raise ValueError(f'safety limits max_jog_joint_step_deg must be positive: {source}')
    if limits.max_gripper_force <= 0.0:
        raise ValueError(f'safety limits max_gripper_force must be positive: {source}')
    return limits
