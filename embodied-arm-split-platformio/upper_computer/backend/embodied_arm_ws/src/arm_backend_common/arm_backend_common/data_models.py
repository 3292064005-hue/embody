from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TargetSnapshot:
    target_id: str = ""
    target_type: str = ""
    semantic_label: str = ""
    table_x: float = 0.0
    table_y: float = 0.0
    yaw: float = 0.0
    confidence: float = 0.0
    image_u: float = 0.0
    image_v: float = 0.0
    received_monotonic: float = field(default_factory=time.monotonic)
    version: int = 0

    def is_fresh(self, stale_after_sec: float, now: Optional[float] = None) -> bool:
        if stale_after_sec <= 0.0:
            return True
        now = time.monotonic() if now is None else now
        return (now - self.received_monotonic) <= stale_after_sec

    def key(self) -> str:
        return self.target_id or f"{self.target_type}:{self.semantic_label}:{round(self.table_x, 3)}:{round(self.table_y, 3)}"

    def matches_selector(self, selector: str) -> bool:
        selector_norm = selector.strip().lower()
        if not selector_norm:
            return True
        haystack = {
            (self.target_id or "").lower(),
            (self.target_type or "").lower(),
            (self.semantic_label or "").lower(),
        }
        return selector_norm in haystack

    def moved_from(self, other: "TargetSnapshot", tolerance_xy: float = 0.01, tolerance_yaw: float = 0.15) -> bool:
        return (
            abs(self.table_x - other.table_x) > tolerance_xy
            or abs(self.table_y - other.table_y) > tolerance_xy
            or abs(self.yaw - other.yaw) > tolerance_yaw
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "semantic_label": self.semantic_label,
            "table_x": self.table_x,
            "table_y": self.table_y,
            "yaw": self.yaw,
            "confidence": self.confidence,
            "image_u": self.image_u,
            "image_v": self.image_v,
            "received_monotonic": self.received_monotonic,
            "version": self.version,
        }


@dataclass
class HardwareSnapshot:
    stm32_online: bool = False
    esp32_online: bool = False
    estop_pressed: bool = False
    home_ok: bool = False
    gripper_ok: bool = False
    motion_busy: bool = False
    limit_triggered: bool = False
    hardware_fault_code: int = 0
    raw_status: str = ""
    updated_monotonic: float = field(default_factory=time.monotonic)
    last_result: str = ""
    last_kind: str = ""
    last_stage: str = ""
    last_sequence: int = -1
    task_id: str = ""

    def is_ready(self, stale_after_sec: float = 1.2, now: Optional[float] = None) -> bool:
        if not self.stm32_online:
            return False
        if self.estop_pressed or self.limit_triggered or self.hardware_fault_code != 0:
            return False
        return self.is_fresh(stale_after_sec=stale_after_sec, now=now)

    def is_fresh(self, stale_after_sec: float = 1.2, now: Optional[float] = None) -> bool:
        if stale_after_sec <= 0.0:
            return True
        now = time.monotonic() if now is None else now
        return (now - self.updated_monotonic) <= stale_after_sec


@dataclass
class CalibrationProfile:
    version: str = "default"
    x_bias: float = 0.0
    y_bias: float = 0.0
    yaw_bias: float = 0.0
    pre_grasp_z: float = 0.12
    grasp_z: float = 0.03
    place_z: float = 0.05
    retreat_z: float = 0.12
    place_profiles: Dict[str, Dict[str, float]] = field(default_factory=dict)
    created_at: str = ""
    operator: str = ""
    camera_serial: str = ""
    robot_description_hash: str = ""
    workspace_id: str = "default"
    active: bool = True

    def apply_target(self, x: float, y: float, yaw: float) -> tuple[float, float, float]:
        return x + self.x_bias, y + self.y_bias, yaw + self.yaw_bias

    def resolve_place_profile(self, place_profile: str) -> Dict[str, float]:
        default_profile = self.place_profiles.get("default", {"x": 0.20, "y": 0.0, "yaw": 0.0})
        return dict(self.place_profiles.get(place_profile, default_profile))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "x_bias": self.x_bias,
            "y_bias": self.y_bias,
            "yaw_bias": self.yaw_bias,
            "pre_grasp_z": self.pre_grasp_z,
            "grasp_z": self.grasp_z,
            "place_z": self.place_z,
            "retreat_z": self.retreat_z,
            "place_profiles": self.place_profiles,
            "created_at": self.created_at,
            "operator": self.operator,
            "camera_serial": self.camera_serial,
            "robot_description_hash": self.robot_description_hash,
            "workspace_id": self.workspace_id,
            "active": self.active,
        }


@dataclass
class TaskProfile:
    confidence_threshold: float = 0.75
    stale_target_sec: float = 1.0
    verify_timeout_sec: float = 1.0
    verify_strategy: str = "hardware_or_target_lost"
    clear_table_max_items: int = 20
    ack_timeout_sec: float = 0.35
    completion_timeout_sec: float = 1.2
    selector_to_place_profile: Dict[str, str] = field(default_factory=dict)

    def resolve_place_profile(self, selector: str, fallback: str) -> str:
        if fallback:
            return fallback
        if not selector:
            return "default"
        return self.selector_to_place_profile.get(selector, "default")


@dataclass
class TaskRequest:
    task_id: str
    task_type: str
    target_selector: str = ""
    place_profile: str = "default"
    auto_retry: bool = True
    max_retry: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    correlation_id: str = ""
    task_run_id: str = ""
    queued_monotonic: float = field(default_factory=time.monotonic)


@dataclass
class TaskContext:
    task_id: str = ""
    task_type: str = ""
    target_selector: str = ""
    place_profile: str = "default"
    auto_retry: bool = True
    max_retry: int = 2
    current_retry: int = 0
    target_id: Optional[str] = None
    selected_target: Optional[TargetSnapshot] = None
    active_place_pose: Dict[str, float] = field(default_factory=dict)
    stage: str = ""
    stage_history: List[str] = field(default_factory=list)
    last_message: str = ""
    start_monotonic: float = 0.0
    perception_deadline: float = 0.0
    plan_deadline: float = 0.0
    execute_deadline: float = 0.0
    verify_deadline: float = 0.0
    complete_count: int = 0
    completed_target_ids: set[str] = field(default_factory=set)
    cancel_requested: bool = False
    reserved_target_key: Optional[str] = None
    request_id: str = ""
    correlation_id: str = ""
    task_run_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(cls, request: TaskRequest, start_monotonic: Optional[float] = None) -> "TaskContext":
        return cls(
            task_id=request.task_id,
            task_type=request.task_type,
            target_selector=request.target_selector,
            place_profile=request.place_profile,
            auto_retry=request.auto_retry,
            max_retry=request.max_retry,
            start_monotonic=time.monotonic() if start_monotonic is None else start_monotonic,
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            task_run_id=request.task_run_id,
            metadata=dict(request.metadata),
        )

    def reset_for_retry(
        self,
        now: float,
        target_timeout_sec: float,
        plan_timeout_sec: float,
        execute_timeout_sec: float,
        verify_timeout_sec: float,
    ) -> None:
        self.target_id = None
        self.selected_target = None
        self.active_place_pose = {}
        self.stage = ""
        self.last_message = ""
        self.stage_history = []
        self.reserved_target_key = None
        self.perception_deadline = now + target_timeout_sec
        self.plan_deadline = now + plan_timeout_sec
        self.execute_deadline = now + execute_timeout_sec
        self.verify_deadline = now + verify_timeout_sec

    def is_active(self) -> bool:
        return bool(self.task_id)

    def elapsed(self, now: Optional[float] = None) -> float:
        if self.start_monotonic <= 0.0:
            return 0.0
        now = time.monotonic() if now is None else now
        return max(0.0, now - self.start_monotonic)
