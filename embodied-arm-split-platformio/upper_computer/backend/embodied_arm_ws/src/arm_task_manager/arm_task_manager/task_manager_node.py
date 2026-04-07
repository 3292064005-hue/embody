from __future__ import annotations

import json
import warnings
import time
import uuid
from typing import Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

from arm_backend_common.config import load_yaml
from arm_backend_common.data_models import (
    CalibrationProfile,
    HardwareSnapshot,
    TargetSnapshot,
    TaskContext,
    TaskProfile,
    TaskRequest,
)
from arm_backend_common.enums import FaultCode, SystemMode
from arm_backend_common.error_codes import fault_message
from arm_backend_common.retry_policy import RetryPolicy
from arm_msgs.action import PickPlaceTask
from arm_msgs.msg import HardwareState, SystemState, TargetInfo, TaskEvent
from arm_msgs.srv import HomeArm, ResetFault, StartTask, StopTask

from .mission_queue import MissionQueue
from .recovery import RecoveryManager
from .state_machine import SystemStateMachine
from .target_registry import TargetRegistry
from .target_reservation import TargetReservationManager
from .verification import VerificationManager


class TaskManagerNode(Node):
    def __init__(self) -> None:
        super().__init__("task_manager_node")
        self.declare_parameter("task_profile_path", "")
        self.declare_parameter("target_timeout_sec", 2.0)
        self.declare_parameter("plan_timeout_sec", 2.0)
        self.declare_parameter("execute_timeout_sec", 8.0)
        self.declare_parameter("verify_timeout_sec", 1.0)
        self.declare_parameter("stale_target_sec", 1.0)
        self.declare_parameter("tick_period_sec", 0.1)
        self.declare_parameter("clear_table_max_items", 20)
        self.declare_parameter("max_queue_size", 8)
        self.declare_parameter("target_lock_timeout_sec", 3.0)
        self.declare_parameter("hardware_fresh_sec", 1.2)
        self.declare_parameter("enable_target_registry", True)

        self._state_machine = SystemStateMachine()
        self._task = TaskContext()
        self._queue = MissionQueue(max_size=int(self.get_parameter("max_queue_size").value))
        self._target_registry = TargetRegistry()
        self._reservations = TargetReservationManager(reserve_timeout_sec=float(self.get_parameter("target_lock_timeout_sec").value))
        self._verification = VerificationManager()
        self._recovery = RecoveryManager()
        self._task_profile = TaskProfile(selector_to_place_profile={"red": "bin_red", "blue": "bin_blue", "green": "default"})
        self._load_task_profile()
        self._latest_target: Optional[TargetSnapshot] = None
        self._hardware = HardwareSnapshot()
        self._calibration = CalibrationProfile()
        self._active_goal_handle = None
        self._goal_request_sent = False
        self._execution_result_received = False
        self._execution_success = False
        self._execution_message = ""
        self._cancel_requested = False
        self._last_goal_task_id = ""

        self._state_pub = self.create_publisher(SystemState, "/arm/system/state", 20)
        self._event_pub = self.create_publisher(TaskEvent, "/arm/log/event", 50)
        self._hardware_cmd_pub = self.create_publisher(String, "/arm/hardware/command", 20)
        self._summary_pub = self.create_publisher(String, "/arm/task_manager/summary", 10)

        self.create_subscription(TargetInfo, "/arm/vision/target", self._on_target, 20)
        self.create_subscription(HardwareState, "/arm/hardware/state", self._on_hardware_state, 20)
        self.create_subscription(String, "/arm/calibration/profile", self._on_calibration_profile, 10)
        self.create_subscription(String, "/arm/profiles/active", self._on_profiles_active, 10)

        self.create_service(StartTask, "/arm/start_task", self._handle_start_task)
        self.create_service(ResetFault, "/arm/reset_fault", self._handle_reset_fault)
        self.create_service(StopTask, "/arm/stop_task", self._handle_stop_task)
        self.create_service(HomeArm, "/arm/home", self._handle_home)

        self._motion_client = ActionClient(self, PickPlaceTask, "/arm/pick_place_task")
        tick_period = float(self.get_parameter("tick_period_sec").value)
        self.create_timer(tick_period, self._tick)
        self.create_timer(0.2, self._publish_system_state)
        self.create_timer(0.5, self._publish_summary)

        transition = self._state_machine.to_idle()
        self._task.last_message = transition.reason
        self._emit_event("INFO", "system", "STATE_TRANSITION", "", 0, transition.reason)

    def _load_task_profile(self) -> None:
        path = self.get_parameter("task_profile_path").get_parameter_value().string_value
        if not path:
            return
        try:
            cfg = load_yaml(path).data
            self._apply_task_profile_payload(cfg)
            self.get_logger().info(f"Loaded task profile from {path}")
        except Exception as exc:
            self.get_logger().warn(f"Failed to load task profile {path}: {exc}")

    def _apply_task_profile_payload(self, cfg: dict) -> None:
        place_profiles = cfg.get("place_profiles", {})
        self._task_profile = TaskProfile(
            confidence_threshold=float(cfg.get("confidence_threshold", 0.75)),
            stale_target_sec=float(cfg.get("stale_target_sec", self.get_parameter("stale_target_sec").value)),
            verify_timeout_sec=float(cfg.get("verify_timeout_sec", self.get_parameter("verify_timeout_sec").value)),
            verify_strategy=str(cfg.get("verify_strategy", "hardware_or_target_lost")),
            clear_table_max_items=int(cfg.get("clear_table_max_items", self.get_parameter("clear_table_max_items").value)),
            ack_timeout_sec=float(cfg.get("ack_timeout_sec", 0.35)),
            completion_timeout_sec=float(cfg.get("completion_timeout_sec", 1.2)),
            selector_to_place_profile={str(k): str(v) for k, v in place_profiles.items()},
        )

    def _on_profiles_active(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            task_profile = payload.get("task_profile", {})
            placement_profiles = payload.get("placement_profiles", {})
            self._apply_task_profile_payload(task_profile)
            if placement_profiles:
                self._calibration.place_profiles.update({str(k): dict(v) for k, v in placement_profiles.items()})
        except Exception as exc:
            self.get_logger().warn(f"Failed to parse /arm/profiles/active: {exc}")

    def _on_target(self, msg: TargetInfo) -> None:
        if not msg.is_valid:
            return
        version = self._latest_target.version + 1 if self._latest_target else 1
        target = TargetSnapshot(
            target_id=msg.target_id,
            target_type=msg.target_type,
            semantic_label=msg.semantic_label,
            table_x=msg.table_x,
            table_y=msg.table_y,
            yaw=msg.yaw,
            confidence=msg.confidence,
            image_u=msg.image_u,
            image_v=msg.image_v,
            received_monotonic=time.monotonic(),
            version=version,
        )
        self._latest_target = target
        if bool(self.get_parameter("enable_target_registry").value):
            self._target_registry.upsert(target)

    def _on_hardware_state(self, msg: HardwareState) -> None:
        raw: dict = {}
        try:
            raw = json.loads(msg.raw_status) if msg.raw_status else {}
        except Exception:
            raw = {}
        self._hardware = HardwareSnapshot(
            stm32_online=msg.stm32_online,
            esp32_online=msg.esp32_online,
            estop_pressed=msg.estop_pressed,
            home_ok=msg.home_ok,
            gripper_ok=msg.gripper_ok,
            motion_busy=msg.motion_busy,
            limit_triggered=msg.limit_triggered,
            hardware_fault_code=int(msg.hardware_fault_code),
            raw_status=msg.raw_status,
            updated_monotonic=time.monotonic(),
            last_result=str(raw.get("last_result", "")),
            last_kind=str(raw.get("last_kind", "")),
            last_stage=str(raw.get("last_stage", "")),
            last_sequence=int(raw.get("last_sequence", -1)),
            task_id=str(raw.get("task_id", "")),
        )
        if msg.estop_pressed:
            self._enter_fault(FaultCode.ESTOP_TRIGGERED)
        elif msg.limit_triggered:
            self._enter_fault(FaultCode.HARDWARE_LIMIT_TRIGGERED)
        elif int(msg.hardware_fault_code) != 0:
            self._enter_fault(FaultCode.UNKNOWN, detail=f"Hardware fault code {msg.hardware_fault_code}")

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

    def _handle_start_task(self, request: StartTask.Request, response: StartTask.Response) -> StartTask.Response:
        if self._state_machine.mode == SystemMode.FAULT:
            response.accepted = False
            response.task_id = ""
            response.message = "System in FAULT; reset fault first"
            return response

        task_id = uuid.uuid4().hex[:12]
        queued = self._queue.push(TaskRequest(
            task_id=task_id,
            task_type=request.task_type,
            target_selector=request.target_selector,
            place_profile=self._task_profile.resolve_place_profile(request.target_selector, request.place_profile),
            auto_retry=bool(request.auto_retry),
            max_retry=max(0, int(request.max_retry or 2)),
        ))
        if not queued:
            response.accepted = False
            response.task_id = ""
            response.message = "Task queue full"
            return response

        self._emit_event("INFO", "task_manager", "TASK_ENQUEUED", task_id, 0, f"Queued task type={request.task_type}")
        response.accepted = True
        response.task_id = task_id
        response.message = "Task queued"
        return response

    def _handle_reset_fault(self, request: ResetFault.Request, response: ResetFault.Response) -> ResetFault.Response:
        del request
        self._queue.clear()
        self._clear_active_task()
        self._cancel_requested = False
        self._send_hardware_command({"kind": "RESET_FAULT", "task_id": "system", "timeout_sec": 0.6})
        transition = self._state_machine.to_idle("Fault reset; system back to IDLE")
        self._emit_event("WARN", "task_manager", "FAULT_RESET", "", 0, transition.reason)
        response.success = True
        response.message = transition.reason
        return response

    def _handle_stop_task(self, request: StopTask.Request, response: StopTask.Response) -> StopTask.Response:
        del request
        self._queue.clear()
        self._cancel_requested = True
        self._task.cancel_requested = True
        transition = self._state_machine.safe_stop("Task stop requested")
        self._task.last_message = transition.reason
        self._emit_event("WARN", "task_manager", "SAFE_STOP", self._task.task_id, 0, transition.reason)
        self._send_hardware_command({"kind": "STOP", "task_id": self._task.task_id or "system", "timeout_sec": 0.4})
        if self._active_goal_handle is not None:
            self._active_goal_handle.cancel_goal_async()
        response.success = True
        response.message = "Task stopped"
        return response

    def _handle_home(self, request: HomeArm.Request, response: HomeArm.Response) -> HomeArm.Response:
        del request
        self._send_hardware_command({"kind": "HOME", "task_id": self._task.task_id or "system", "timeout_sec": 1.0})
        response.success = True
        response.message = "HOME command dispatched"
        return response

    def _tick(self) -> None:
        if self._state_machine.mode == SystemMode.FAULT:
            return
        if self._state_machine.mode == SystemMode.SAFE_STOP:
            if not self._hardware.motion_busy and self._queue.is_empty() and not self._task.is_active():
                transition = self._state_machine.to_idle("Recovered from safe stop")
                self._emit_event("INFO", "task_manager", "STATE_TRANSITION", "", 0, transition.reason)
            return

        if self._state_machine.mode == SystemMode.IDLE:
            self._start_next_task_if_needed()
            return

        if self._cancel_requested:
            return
        if self._state_machine.mode == SystemMode.PERCEPTION:
            self._tick_perception()
        elif self._state_machine.mode == SystemMode.PLAN:
            self._tick_plan()
        elif self._state_machine.mode == SystemMode.EXECUTE:
            self._tick_execute()
        elif self._state_machine.mode == SystemMode.VERIFY:
            self._tick_verify()

    def _start_next_task_if_needed(self) -> None:
        if self._task.is_active():
            return
        queued = self._queue.pop()
        if queued is None:
            return
        now = time.monotonic()
        self._task = TaskContext.from_request(queued, start_monotonic=now)
        self._task.reset_for_retry(
            now=now,
            target_timeout_sec=float(self.get_parameter("target_timeout_sec").value),
            plan_timeout_sec=float(self.get_parameter("plan_timeout_sec").value),
            execute_timeout_sec=float(self.get_parameter("execute_timeout_sec").value),
            verify_timeout_sec=self._task_profile.verify_timeout_sec,
        )
        self._reset_motion_request_state()
        self._cancel_requested = False
        transition = self._state_machine.start_task()
        self._task.last_message = transition.reason
        self._emit_event("INFO", "task_manager", "TASK_START", self._task.task_id, 0, transition.reason)

    def _tick_perception(self) -> None:
        now = time.monotonic()
        hardware_fresh_sec = float(self.get_parameter("hardware_fresh_sec").value)
        if not self._hardware.is_ready(stale_after_sec=hardware_fresh_sec, now=now):
            if now > self._task.perception_deadline:
                self._retry_or_fault(FaultCode.SERIAL_DISCONNECTED, "Hardware not ready for task execution")
            return
        target = self._select_target(now)
        if target is not None:
            self._task.target_id = target.target_id
            self._task.selected_target = target
            self._task.reserved_target_key = target.key()
            self._task.active_place_pose = self._calibration.resolve_place_profile(self._task.place_profile)
            self._reservations.refresh(self._task.task_id, target, now)
            transition = self._state_machine.perception_ok(f"Target {target.target_id or target.semantic_label or target.target_type} locked")
            self._task.last_message = transition.reason
            self._emit_event("INFO", "task_manager", "PERCEPTION_OK", self._task.task_id, 0, transition.reason)
            return
        if now > self._task.perception_deadline:
            self._retry_or_fault(FaultCode.TARGET_NOT_FOUND, "No matching target before perception deadline")

    def _tick_plan(self) -> None:
        now = time.monotonic()
        selected = self._task.selected_target
        if selected is None or not selected.is_fresh(self._task_profile.stale_target_sec + 0.5, now=now):
            self._retry_or_fault(FaultCode.TARGET_STALE, "Target disappeared before planning")
            return
        if not self._motion_client.server_is_ready():
            if now > self._task.plan_deadline:
                self._retry_or_fault(FaultCode.MOTION_SERVER_UNAVAILABLE, "Motion bridge unavailable")
            return
        if self._goal_request_sent:
            return
        goal = PickPlaceTask.Goal()
        goal.task_id = self._task.task_id
        goal.target_type = selected.target_type
        goal.target_id = selected.target_id
        goal.target_x = selected.table_x
        goal.target_y = selected.table_y
        goal.target_yaw = selected.yaw
        goal.place_profile = self._task.place_profile
        goal.max_retry = self._task.max_retry
        future = self._motion_client.send_goal_async(goal, feedback_callback=self._motion_feedback)
        future.add_done_callback(self._on_goal_response)
        self._goal_request_sent = True
        self._last_goal_task_id = self._task.task_id
        transition = self._state_machine.planning_stage("PLAN_GRASP", "Motion goal sent")
        self._task.last_message = transition.reason

    def _tick_execute(self) -> None:
        if self._execution_result_received:
            if self._execution_success:
                transition = self._state_machine.execute_ok(self._execution_message or "Execution completed")
                self._task.last_message = transition.reason
                self._emit_event("INFO", "task_manager", "EXECUTE_OK", self._task.task_id, 0, transition.reason)
            else:
                self._retry_or_fault(FaultCode.EXECUTE_TIMEOUT, self._execution_message or "Execution failed")
            return
        if time.monotonic() > self._task.execute_deadline:
            if self._active_goal_handle is not None:
                self._active_goal_handle.cancel_goal_async()
            self._retry_or_fault(FaultCode.EXECUTE_TIMEOUT, "Execution deadline exceeded")

    def _tick_verify(self) -> None:
        now = time.monotonic()
        result = self._verification.verify(
            task=self._task,
            profile=self._task_profile,
            hardware=self._hardware,
            latest_target=self._latest_target,
            now=now,
        )
        if not result.finished:
            self._task.last_message = result.message
            return
        if not result.success:
            self._retry_or_fault(FaultCode.GRIPPER_FAILURE, result.message)
            return

        self._task.complete_count += 1
        if self._task.target_id:
            self._task.completed_target_ids.add(self._task.target_id)
        if self._task.selected_target is not None:
            self._target_registry.mark_consumed(self._task.selected_target.key())
        self._reservations.release(self._task.task_id, self._task.selected_target)

        if str(self._task.task_type).upper() == "CLEAR_TABLE":
            if self._task.complete_count < self._task_profile.clear_table_max_items:
                transition = self._state_machine.retry_to_perception("CLEAR_TABLE continuing with next target")
                self._task.last_message = transition.reason
                now = time.monotonic()
                self._task.reset_for_retry(
                    now=now,
                    target_timeout_sec=float(self.get_parameter("target_timeout_sec").value),
                    plan_timeout_sec=float(self.get_parameter("plan_timeout_sec").value),
                    execute_timeout_sec=float(self.get_parameter("execute_timeout_sec").value),
                    verify_timeout_sec=self._task_profile.verify_timeout_sec,
                )
                self._reset_motion_request_state()
                self._emit_event("INFO", "task_manager", "CLEAR_TABLE_CONTINUE", self._task.task_id, 0, transition.reason)
                return
        transition = self._state_machine.verify_ok("Task verified and completed")
        self._task.last_message = transition.reason
        self._emit_event("INFO", "task_manager", "TASK_DONE", self._task.task_id, 0, transition.reason)
        self._clear_active_task(last_message=transition.reason)

    def _select_target(self, now: float) -> Optional[TargetSnapshot]:
        selector = (self._task.target_selector or "").strip().lower()
        candidates = list(self._target_registry.find_matching(selector, self._task_profile.stale_target_sec, now))
        if not candidates and self._latest_target is not None:
            candidates = [self._latest_target]
        for target in candidates:
            if not target.is_fresh(self._task_profile.stale_target_sec, now=now):
                continue
            if target.confidence < self._task_profile.confidence_threshold:
                continue
            if selector and not target.matches_selector(selector):
                if str(self._task.task_type).upper() != "CLEAR_TABLE":
                    continue
            if target.target_id in self._task.completed_target_ids:
                continue
            if self._reservations.is_reserved(target, now=now) and (not self._task.selected_target or target.key() != self._task.selected_target.key()):
                continue
            if not self._reservations.reserve(self._task.task_id, target, now=now):
                continue
            return target
        return None

    def _reset_motion_request_state(self) -> None:
        self._active_goal_handle = None
        self._goal_request_sent = False
        self._execution_result_received = False
        self._execution_success = False
        self._execution_message = ""
        self._last_goal_task_id = ""

    def _retry_or_fault(self, code: FaultCode, message: str) -> None:
        if self._task.auto_retry and self._task.current_retry < self._task.max_retry:
            self._task.current_retry += 1
            retry_policy = RetryPolicy(max_attempts=self._task.max_retry + 1)
            backoff = retry_policy.next_backoff(self._task.current_retry)
            self._reservations.release(self._task.task_id, self._task.selected_target)
            transition = self._state_machine.retry_to_perception(f"Retry {self._task.current_retry}/{self._task.max_retry}: {message}")
            self._task.last_message = transition.reason
            self._emit_event("WARN", "task_manager", "TASK_RETRY", self._task.task_id, int(code), transition.reason)
            self._reset_motion_request_state()
            now = time.monotonic() + backoff
            self._task.reset_for_retry(
                now=now,
                target_timeout_sec=float(self.get_parameter("target_timeout_sec").value),
                plan_timeout_sec=float(self.get_parameter("plan_timeout_sec").value),
                execute_timeout_sec=float(self.get_parameter("execute_timeout_sec").value),
                verify_timeout_sec=self._task_profile.verify_timeout_sec,
            )
        else:
            self._enter_fault(code, detail=message)

    def _on_goal_response(self, future) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._retry_or_fault(FaultCode.PLAN_FAILED, f"Goal response failure: {exc}")
            return
        if self._task.task_id != self._last_goal_task_id:
            return
        if goal_handle is None or not goal_handle.accepted:
            self._retry_or_fault(FaultCode.PLAN_FAILED, "Motion goal rejected")
            return
        self._active_goal_handle = goal_handle
        transition = self._state_machine.plan_ok("Motion goal accepted")
        self._task.last_message = transition.reason
        self._emit_event("INFO", "task_manager", "PLAN_OK", self._task.task_id, 0, transition.reason)
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_motion_result)

    def _on_motion_result(self, future) -> None:
        try:
            wrapped = future.result()
        except Exception as exc:
            self._execution_result_received = True
            self._execution_success = False
            self._execution_message = f"Motion result future failed: {exc}"
            return
        if self._task.task_id != self._last_goal_task_id:
            return
        result = wrapped.result
        self._execution_result_received = True
        self._execution_success = bool(result.success)
        self._execution_message = result.message

    def _motion_feedback(self, feedback_msg) -> None:
        fb = feedback_msg.feedback
        self._task.stage = fb.stage
        self._task.stage_history.append(fb.stage)
        self._task.last_message = fb.message
        self._state_machine.executing_stage(fb.stage or "EXECUTING", fb.message or "Motion feedback")
        self._emit_event("INFO", "motion_bridge", "EXEC_STAGE", self._task.task_id, 0, f"{fb.stage}: {fb.message}")

    def _enter_fault(self, code: FaultCode, detail: str | None = None) -> None:
        message = detail or fault_message(int(code))
        decision = self._recovery.decide(code, message)
        if decision.publish_stop:
            self._send_hardware_command({"kind": "STOP", "task_id": self._task.task_id or "system", "timeout_sec": 0.3})
        if decision.publish_home and not self._hardware.motion_busy:
            self._send_hardware_command({"kind": "HOME", "task_id": self._task.task_id or "system", "timeout_sec": 0.8})
        transition = self._state_machine.fault(code, decision.message)
        self._task.last_message = transition.reason
        self._emit_event("ERROR", "task_manager", "FAULT", self._task.task_id, int(transition.fault), transition.reason)
        self._queue.clear()
        self._reservations.release(self._task.task_id, self._task.selected_target)

    def _clear_active_task(self, last_message: str = "") -> None:
        self._reservations.release(self._task.task_id, self._task.selected_target)
        self._task = TaskContext(last_message=last_message)
        self._reset_motion_request_state()
        self._cancel_requested = False

    def _send_hardware_command(self, payload: dict) -> None:
        self._hardware_cmd_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _emit_event(self, level: str, source: str, event_type: str, task_id: str, code: int, message: str) -> None:
        event = TaskEvent()
        event.level = level
        event.source = source
        event.event_type = event_type
        event.task_id = task_id
        event.code = code
        event.message = message
        event.stamp = self.get_clock().now().to_msg()
        self._event_pub.publish(event)

    def _publish_system_state(self) -> None:
        msg = SystemState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.system_mode = int(self._state_machine.mode)
        msg.current_task_id = self._task.task_id
        msg.current_stage = self._task.stage or self._state_machine.phase
        hardware_fresh_sec = float(self.get_parameter("hardware_fresh_sec").value)
        msg.hardware_ready = self._hardware.is_ready(stale_after_sec=hardware_fresh_sec)
        msg.motion_ready = self._motion_client.server_is_ready()
        msg.calibration_ready = bool(self._calibration.version)
        msg.vision_ready = bool(self._latest_target and self._latest_target.is_fresh(self._task_profile.stale_target_sec))
        msg.emergency_stop = self._state_machine.mode == SystemMode.SAFE_STOP or self._hardware.estop_pressed
        msg.active_fault_code = int(self._state_machine.last_fault)
        queue_sz = self._queue.size()
        msg.message = f"{self._task.last_message or self._state_machine.last_reason} | phase={self._state_machine.phase} | queue={queue_sz}"
        self._state_pub.publish(msg)

    def _publish_summary(self) -> None:
        payload = {
            "system_mode": int(self._state_machine.mode),
            "phase": self._state_machine.phase,
            "queue_size": self._queue.size(),
            "task_id": self._task.task_id,
            "task_type": self._task.task_type,
            "current_retry": self._task.current_retry,
            "completed_targets": len(self._task.completed_target_ids),
            "last_message": self._task.last_message or self._state_machine.last_reason,
            "hardware_ready": self._hardware.is_ready(stale_after_sec=float(self.get_parameter("hardware_fresh_sec").value)),
            "vision_ready": bool(self._latest_target and self._latest_target.is_fresh(self._task_profile.stale_target_sec)),
        }
        self._summary_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))


def main(args=None) -> None:
    warnings.warn('This node is deprecated. Use the split-stack replacement packages instead.', DeprecationWarning, stacklevel=2)
    rclpy.init(args=args)
    node = TaskManagerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
