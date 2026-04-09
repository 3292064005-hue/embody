from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from arm_backend_common.data_models import HardwareSnapshot, TargetSnapshot, TaskContext, TaskProfile


@dataclass
class VerificationResult:
    finished: bool
    success: bool
    message: str


class VerificationManager:
    def verify(
        self,
        task: TaskContext,
        profile: TaskProfile,
        hardware: HardwareSnapshot,
        latest_target: Optional[TargetSnapshot],
        now: float,
    ) -> VerificationResult:
        if now < task.verify_deadline and hardware.motion_busy:
            return VerificationResult(False, False, "Waiting for motion to settle")

        strategy = profile.verify_strategy.strip().lower() or "hardware_or_target_lost"
        if strategy == "target_pose_changed":
            if latest_target is None or task.selected_target is None:
                return VerificationResult(True, True, "Target no longer visible after execution")
            if latest_target.key() != task.selected_target.key():
                return VerificationResult(True, True, "Another target is visible; selected target disappeared")
            if latest_target.moved_from(task.selected_target):
                return VerificationResult(True, True, "Target pose changed after grasp, treated as success")
            return VerificationResult(True, False, "Target still visible at original pose")

        if strategy == "gripper_then_target_lost":
            if not hardware.gripper_ok:
                return VerificationResult(True, False, "Gripper did not confirm closure")
            if latest_target is None or task.selected_target is None or latest_target.key() != task.selected_target.key():
                return VerificationResult(True, True, "Gripper confirmed and target disappeared")
            if not latest_target.is_fresh(profile.stale_target_sec, now=now):
                return VerificationResult(True, True, "Gripper confirmed and target became stale")
            return VerificationResult(True, False, "Target still visible after gripper closure")

        if latest_target is not None and task.selected_target is not None and latest_target.key() == task.selected_target.key():
            if latest_target.is_fresh(profile.stale_target_sec, now=now):
                return VerificationResult(True, False, "Target still visible after execution")
        if not hardware.is_ready(now=now):
            return VerificationResult(True, False, "Hardware not healthy during verification")
        return VerificationResult(True, True, "Verification passed")
