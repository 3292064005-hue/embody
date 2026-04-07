from __future__ import annotations

import json
import warnings
import threading
import time
from typing import Any, Dict

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.node import Node
from std_msgs.msg import String

from arm_backend_common.data_models import CalibrationProfile
from arm_backend_common.enums import FaultCode
from arm_msgs.action import PickPlaceTask
from arm_msgs.msg import HardwareState
from .result_mapper import map_stage_failure
from .stage_builder import MotionStage, StageBuilder


class MotionBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("motion_bridge_node")
        self.declare_parameter("stage_timeout_sec", 1.2)
        self.declare_parameter("ack_timeout_sec", 0.35)
        self._feedback_lock = threading.Condition()
        self._feedback_by_key: dict[tuple[str, str, str], Dict[str, Any]] = {}
        self._hardware_state = HardwareState()
        self._calibration = CalibrationProfile(
            place_profiles={
                "bin_red": {"x": 0.25, "y": 0.12, "yaw": 0.0},
                "bin_blue": {"x": 0.25, "y": -0.12, "yaw": 0.0},
                "default": {"x": 0.20, "y": 0.0, "yaw": 0.0},
            }
        )
        self._command_pub = self.create_publisher(String, "/arm/hardware/command", 20)
        self.create_subscription(String, "/arm/hardware/feedback", self._on_hardware_feedback, 50)
        self.create_subscription(String, "/arm/calibration/profile", self._on_calibration_profile, 10)
        self.create_subscription(String, "/arm/profiles/active", self._on_profiles_active, 10)
        self.create_subscription(HardwareState, "/arm/hardware/state", self._on_hardware_state, 20)
        self._server = ActionServer(
            self,
            PickPlaceTask,
            "/arm/pick_place_task",
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
        )
        self.get_logger().info("Motion bridge action server is ready.")

    def goal_callback(self, goal_request: PickPlaceTask.Goal) -> GoalResponse:
        del goal_request
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle) -> CancelResponse:
        del goal_handle
        return CancelResponse.ACCEPT

    def _on_hardware_feedback(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except Exception:
            return
        key = (
            str(payload.get("task_id", "")),
            str(payload.get("stage", "")),
            str(payload.get("kind", "")),
        )
        with self._feedback_lock:
            self._feedback_by_key[key] = payload
            self._feedback_lock.notify_all()

    def _on_calibration_profile(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            profile = payload.get("profile", {})
            self._calibration = CalibrationProfile(
                version=str(profile.get("version", "default")),
                x_bias=float(profile.get("x_bias", 0.0)),
                y_bias=float(profile.get("y_bias", 0.0)),
                yaw_bias=float(profile.get("yaw_bias", 0.0)),
                pre_grasp_z=float(profile.get("pre_grasp_z", 0.12)),
                grasp_z=float(profile.get("grasp_z", 0.03)),
                place_z=float(profile.get("place_z", 0.05)),
                retreat_z=float(profile.get("retreat_z", 0.12)),
                place_profiles=dict(profile.get("place_profiles", self._calibration.place_profiles)),
            )
        except Exception as exc:
            self.get_logger().warn(f"Failed to parse calibration profile: {exc}")

    def _on_profiles_active(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            placement_profiles = payload.get("placement_profiles", {})
            if placement_profiles:
                self._calibration.place_profiles.update({str(k): dict(v) for k, v in placement_profiles.items()})
        except Exception as exc:
            self.get_logger().warn(f"Failed to parse /arm/profiles/active: {exc}")

    def _on_hardware_state(self, msg: HardwareState) -> None:
        self._hardware_state = msg

    async def execute_callback(self, goal_handle):
        start = time.monotonic()
        req = goal_handle.request
        x, y, yaw = self._calibration.apply_target(req.target_x, req.target_y, req.target_yaw)
        stages = StageBuilder(self._calibration).build_pick_and_place(x=x, y=y, yaw=yaw, place_profile=req.place_profile)

        total = len(stages)
        for idx, stage in enumerate(stages, start=1):
            if goal_handle.is_cancel_requested:
                self._publish_stop(req.task_id)
                goal_handle.canceled()
                result = PickPlaceTask.Result()
                result.success = False
                result.result_code = int(FaultCode.EXECUTE_CANCELED)
                result.message = "Motion canceled by client"
                result.total_time = float(time.monotonic() - start)
                return result

            feedback = PickPlaceTask.Feedback()
            feedback.stage = stage.stage
            feedback.progress = float(idx - 1) / float(total)
            feedback.message = f"Dispatching stage {stage.stage}"
            feedback.retry_count = 0
            goal_handle.publish_feedback(feedback)

            ok, reason = self._dispatch_and_wait(req.task_id, stage)
            feedback.progress = float(idx) / float(total)
            feedback.message = reason
            goal_handle.publish_feedback(feedback)
            if not ok:
                self._publish_stop(req.task_id)
                goal_handle.abort()
                result = PickPlaceTask.Result()
                result.success = False
                result.result_code = int(map_stage_failure(reason))
                result.message = reason
                result.total_time = float(time.monotonic() - start)
                return result

            if stage.stage == "CLOSE_GRIPPER" and not self._hardware_state.gripper_ok:
                self._publish_stop(req.task_id)
                goal_handle.abort()
                result = PickPlaceTask.Result()
                result.success = False
                result.result_code = int(FaultCode.GRIPPER_FAILURE)
                result.message = "Gripper verification failed after CLOSE_GRIPPER"
                result.total_time = float(time.monotonic() - start)
                return result

        goal_handle.succeed()
        result = PickPlaceTask.Result()
        result.success = True
        result.result_code = 0
        result.message = "Motion sequence executed successfully"
        result.total_time = float(time.monotonic() - start)
        return result

    def _dispatch_and_wait(self, task_id: str, stage: MotionStage) -> tuple[bool, str]:
        payload = stage.to_payload()
        payload.update({
            "task_id": task_id,
            "ack_timeout_sec": float(self.get_parameter("ack_timeout_sec").value),
        })
        msg = String(data=json.dumps(payload, ensure_ascii=False))
        lookup_key = (task_id, stage.stage, stage.kind)
        with self._feedback_lock:
            self._feedback_by_key.pop(lookup_key, None)
        self._command_pub.publish(msg)

        ack_seen = False
        ack_deadline = time.monotonic() + float(self.get_parameter("ack_timeout_sec").value)
        done_deadline = time.monotonic() + stage.timeout_sec + 0.8
        with self._feedback_lock:
            while time.monotonic() < done_deadline:
                latest = self._feedback_by_key.get(lookup_key)
                if latest:
                    status = str(latest.get("status", ""))
                    if status == "ack":
                        ack_seen = True
                    elif status == "retry":
                        ack_seen = False
                    elif status == "done":
                        return True, f"{stage.stage} done"
                    elif status == "nack":
                        return False, latest.get("message", f"{stage.stage} NACK")
                    elif status == "timeout":
                        return False, f"{stage.stage} timeout"
                    elif status == "fault":
                        return False, latest.get("message", f"{stage.stage} hardware fault")
                now = time.monotonic()
                if not ack_seen and now > ack_deadline:
                    return False, f"{stage.stage} ack timeout"
                remaining = done_deadline - now
                if remaining <= 0:
                    break
                self._feedback_lock.wait(timeout=min(remaining, 0.1))
        return False, f"{stage.stage} timeout"

    def _publish_stop(self, task_id: str) -> None:
        self._command_pub.publish(String(data=json.dumps({
            "kind": "STOP",
            "task_id": task_id,
            "timeout_sec": 0.4,
        }, ensure_ascii=False)))


def main(args=None) -> None:
    warnings.warn('This node is deprecated. Use the split-stack replacement packages instead.', DeprecationWarning, stacklevel=2)
    rclpy.init(args=args)
    node = MotionBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
