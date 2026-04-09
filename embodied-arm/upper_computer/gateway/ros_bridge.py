from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any

from .models import build_command_summary, coerce_system_state_aliases, default_readiness, map_camera_frame_summary, map_hardware_state_message, map_log_event_message, map_system_state_message, map_target_message, now_iso
from .runtime_bootstrap import simulated_local_only_snapshot
from .runtime_ingress import bind_runtime_ingress
from .ros_contract import (
    ActionNames, ActivateCalibrationVersion, CalibrationProfileMsg, DiagnosticsSummary, HardwareState, HomeArm, Homing, PickPlaceTask, ReadinessState, Recover, ResetFault,
    ServiceNames, SetMode, StartTask, StopTask, SystemState, TargetArray, TargetInfo, TaskEvent, TaskStatus, TopicNames,
)
from .runtime_publisher import RuntimeEventPublisher
from .runtime_codec import (
    decode_calibration_profile_message,
    decode_diagnostics_summary_message,
    decode_readiness_message,
    decode_target_array_message,
    decode_task_status_message,
)
from .runtime_translators import (
    apply_calibration_payload,
    apply_diagnostics_payload,
    apply_readiness_payload,
    apply_targets_payload,
    apply_task_status_payload,
)
from .state import GatewayState

try:
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from std_msgs.msg import String
    from std_srvs.srv import Trigger
    RCLPY_AVAILABLE = True
except Exception:  # pragma: no cover
    rclpy = None
    ActionClient = object
    MultiThreadedExecutor = object
    Node = object
    String = object
    Trigger = object
    HomeArm = ResetFault = SetMode = StartTask = StopTask = ActivateCalibrationVersion = object
    PickPlaceTask = Homing = Recover = object
    CalibrationProfileMsg = DiagnosticsSummary = HardwareState = ReadinessState = SystemState = TargetArray = TargetInfo = TaskEvent = TaskStatus = object
    RCLPY_AVAILABLE = False


class RosBridgeError(RuntimeError):
    pass


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ''):
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ''):
            return float(default)
        converted = float(value)
    except (TypeError, ValueError):
        return float(default)
    if converted != converted:
        return float(default)
    return converted


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'on', 'ok', 'ready'}:
            return True
        if normalized in {'false', '0', 'no', 'off', 'fault', 'degraded', ''}:
            return False
    return bool(value)


def wait_for_ros_future(future, timeout_sec: float) -> None:
    """Block until a ROS future completes or the timeout expires.

    Args:
        future: Future-like object implementing ``add_done_callback`` and ``done``.
        timeout_sec: Maximum number of seconds to wait for completion.

    Returns:
        None. The helper only coordinates completion waiting.

    Raises:
        No exception is raised directly. Callers must inspect ``future.done()``
        and ``future.exception()`` after the wait to decide whether to surface a
        protocol error or timeout.

    Boundary behavior:
        If the callback is never triggered within ``timeout_sec``, the function
        returns without mutating the future so callers can raise a deterministic
        timeout error.
    """
    event = threading.Event()
    future.add_done_callback(lambda _: event.set())
    event.wait(timeout=timeout_sec)


async def resolve_ros_service_call(client, request, *, timeout_sec: float = 3.0):
    """Resolve a ROS service call with explicit unavailable/timeout semantics.

    Args:
        client: Service client exposing ``wait_for_service`` and ``call_async``.
        request: Service request object to submit.
        timeout_sec: Service availability and response timeout in seconds.

    Returns:
        The service response object from ``future.result()``.

    Raises:
        RosBridgeError: If the service is unavailable, times out, or returns an
            exception.

    Boundary behavior:
        The function does not assume the future callback fires; incomplete
        futures are converted into deterministic timeout errors.
    """
    service_name = getattr(client, 'srv_name', '<unknown-service>')
    if not client.wait_for_service(timeout_sec=timeout_sec):
        raise RosBridgeError(f'ROS2 service unavailable: {service_name}')
    future = client.call_async(request)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: wait_for_ros_future(future, timeout_sec))
    if not future.done():
        raise RosBridgeError(f'ROS2 service timeout: {service_name}')
    error = future.exception()
    if error is not None:
        raise RosBridgeError(str(error))
    return future.result()


async def send_ros_action_goal(client, goal, *, wait_for_result: bool, server_timeout_sec: float = 0.5, goal_timeout_sec: float = 3.0, result_timeout_sec: float = 30.0) -> tuple[bool, Any]:
    """Submit a ROS action goal with deterministic timeout/error handling.

    Args:
        client: Action client exposing ``wait_for_server`` and ``send_goal_async``.
        goal: Goal message instance.
        wait_for_result: Whether to wait for the action result before returning.
        server_timeout_sec: Timeout for server discovery.
        goal_timeout_sec: Timeout for goal acceptance.
        result_timeout_sec: Timeout for final result retrieval.

    Returns:
        ``(accepted, result)`` where ``accepted`` is False when the action server
        is absent or the goal is rejected.

    Raises:
        RosBridgeError: If the goal or result future times out or raises.

    Boundary behavior:
        Rejected goals return ``(False, None)`` without raising so existing
        gateway responses preserve their current accepted/rejected semantics.
    """
    action_name = getattr(client, '_action_name', '<unknown-action>')
    if client is None or not client.wait_for_server(timeout_sec=server_timeout_sec):
        return False, None
    goal_future = client.send_goal_async(goal)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: wait_for_ros_future(goal_future, goal_timeout_sec))
    goal_error = goal_future.exception() if goal_future.done() else None
    if not goal_future.done() or goal_error is not None:
        raise RosBridgeError(f'action goal failed: {action_name}')
    goal_handle = goal_future.result()
    if goal_handle is None or not getattr(goal_handle, 'accepted', False):
        return False, None
    if not wait_for_result:
        return True, None
    result_future = goal_handle.get_result_async()
    await loop.run_in_executor(None, lambda: wait_for_ros_future(result_future, result_timeout_sec))
    result_error = result_future.exception() if result_future.done() else None
    if not result_future.done() or result_error is not None:
        raise RosBridgeError(f'action result failed: {action_name}')
    result_msg = result_future.result()
    return True, getattr(result_msg, 'result', result_msg)


def should_route_task_via_pick_place_action(task_type: str) -> bool:
    return str(task_type or '').strip().upper() == 'PICK_AND_PLACE'


def build_pick_place_action_goal_payload(*, task_id: str, target_selector: str, place_profile: str, max_retry: int) -> dict[str, Any]:
    return {
        'task_id': str(task_id),
        # PickPlaceTask.action 没有独立 target_selector 字段；在 action 路径中用 target_type 承载目标类别/选择器，
        # 旧客户端若仍把 task_type 填到 target_type，可由 orchestrator 侧做兼容归一化。
        'target_type': str(target_selector or ''),
        'target_id': '',
        'target_x': 0.0,
        'target_y': 0.0,
        'target_yaw': 0.0,
        'place_profile': str(place_profile),
        'max_retry': max(0, int(max_retry)),
    }


class RosBridge:
    def __init__(self, state: GatewayState, publisher: RuntimeEventPublisher, active_calibration_path: Path) -> None:
        self.state = state
        self.publisher = publisher
        self.active_calibration_path = active_calibration_path
        self.available = RCLPY_AVAILABLE
        self._executor = None
        self._node = None
        self._thread = None
        self._runtime_profile = str(os.environ.get('EMBODIED_ARM_RUNTIME_PROFILE', 'target-runtime') or 'target-runtime').strip().lower()
        self._allow_sim_fallback = os.environ.get('EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK', 'false').lower() == 'true'
        self._simulated_runtime_active = False

    def _can_use_local_simulated_runtime(self) -> bool:
        return self._runtime_profile == 'dev-hmi-mock' and self._allow_sim_fallback

    def _build_simulated_readiness_snapshot(self) -> dict[str, Any]:
        return simulated_local_only_snapshot()

    def start(self) -> None:
        if not self.available:
            system = self.state.get_system()
            system['rosConnected'] = False
            if self._can_use_local_simulated_runtime():
                self._simulated_runtime_active = True
                self.state.set_readiness_snapshot(self._build_simulated_readiness_snapshot(), authoritative=False)
                system['faultMessage'] = 'ROS2 bridge unavailable; gateway running in explicit dev-hmi-mock simulated_local_only profile.'
            else:
                self._simulated_runtime_active = False
                self.state.set_readiness_snapshot(default_readiness(), authoritative=False)
                system['faultMessage'] = 'ROS2 bridge unavailable; gateway remains fail-closed until runtime connectivity is restored.'
            self.state.set_system(system)
            return
        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = GatewayRosNode(self.state, self.publisher)
        self._executor = MultiThreadedExecutor()
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._thread.start()
        system = self.state.get_system()
        system['rosConnected'] = True
        self.state.set_system(system)

    def _record_cleanup_failure(self, component: str, exc: BaseException) -> None:
        """Record a best-effort ROS shutdown failure in the gateway state log."""
        try:
            self.state.append_log(
                {
                    'id': 'log-ros-cleanup',
                    'timestamp': self.state.timestamp(),
                    'level': 'warn',
                    'module': 'gateway.ros_bridge',
                    'taskId': None,
                    'requestId': None,
                    'correlationId': None,
                    'event': 'ros.cleanup_failed',
                    'message': str(exc),
                    'payload': {'component': component, 'exceptionType': exc.__class__.__name__},
                }
            )
        except Exception:
            pass

    def stop(self) -> None:
        """Stop ROS resources without aborting cleanup on intermediate failures.

        Boundary behavior:
            Every cleanup step is attempted at most once. Failures are recorded
            into the gateway log and the remaining resources continue shutting
            down so partial teardown does not leak executor/thread handles.
        """
        if not self.available or self._node is None:
            return
        executor = self._executor
        node = self._node
        thread = self._thread
        self._executor = None
        self._node = None
        self._thread = None
        if executor is not None:
            try:
                executor.shutdown()
            except Exception as exc:
                self._record_cleanup_failure('executor.shutdown', exc)
        if node is not None:
            try:
                node.destroy_node()
            except Exception as exc:
                self._record_cleanup_failure('node.destroy_node', exc)
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception as exc:
            self._record_cleanup_failure('rclpy.shutdown', exc)
        if thread is not None:
            try:
                thread.join(timeout=1.0)
            except Exception as exc:
                self._record_cleanup_failure('thread.join', exc)

    def ensure_available(self) -> None:
        if self.available and self._node is not None:
            return
        if self._simulated_runtime_active:
            return
        raise RosBridgeError('ROS2 bridge unavailable. 请在已 source ROS2 与工作区环境后启动网关，或显式设置 EMBODIED_ARM_RUNTIME_PROFILE=dev-hmi-mock 且开启 EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK=true。')

    async def home(self) -> dict[str, Any]:
        self.ensure_available()
        if self.available and self._node is not None:
            return await self._node.call_home()
        hardware = self.state.get_hardware()
        hardware['homed'] = True
        hardware['busy'] = False
        self.state.set_hardware(hardware)
        return {'success': True, 'message': 'simulated home completed', 'simulated': True}

    async def reset_fault(self) -> dict[str, Any]:
        self.ensure_available()
        if self.available and self._node is not None:
            return await self._node.call_reset_fault()
        system = self.state.get_system()
        system['emergencyStop'] = False
        system['faultCode'] = None
        system['faultMessage'] = None
        system['runtimePhase'] = 'idle'
        system['controllerMode'] = 'idle'
        system['taskStage'] = 'done'
        self.state.set_system(coerce_system_state_aliases(system))
        return {'success': True, 'message': 'simulated fault reset completed', 'simulated': True}


    async def recover(self) -> dict[str, Any]:
        self.ensure_available()
        if self.available and self._node is not None:
            return await self._node.call_recover()
        system = self.state.get_system()
        system['emergencyStop'] = False
        system['faultCode'] = None
        system['faultMessage'] = None
        system['runtimePhase'] = 'idle'
        system['controllerMode'] = 'idle'
        system['taskStage'] = 'done'
        self.state.set_system(coerce_system_state_aliases(system))
        hardware = self.state.get_hardware()
        hardware['busy'] = False
        self.state.set_hardware(hardware)
        return {'success': True, 'message': 'simulated recover completed', 'simulated': True}

    async def stop_task(self) -> dict[str, Any]:
        self.ensure_available()
        if self.available and self._node is not None:
            return await self._node.call_stop_task()
        system = self.state.get_system()
        system['runtimePhase'] = 'safe_stop'
        system['controllerMode'] = 'maintenance'
        system['taskStage'] = 'failed'
        system['faultMessage'] = 'task stopped'
        self.state.set_system(coerce_system_state_aliases(system))
        return {'success': True, 'message': 'simulated task stop completed', 'simulated': True}

    async def emergency_stop(self) -> dict[str, Any]:
        self.ensure_available()
        if self.available and self._node is not None:
            self._node.publish_hardware_command({'kind': 'ESTOP', 'task_id': 'system', 'timeout_sec': 0.2})
            return {'success': True, 'message': 'hardware estop published'}
        system = self.state.get_system()
        system['runtimePhase'] = 'safe_stop'
        system['controllerMode'] = 'maintenance'
        system['taskStage'] = 'failed'
        system['emergencyStop'] = True
        system['faultCode'] = 'ESTOP'
        system['faultMessage'] = 'simulated estop'
        self.state.set_system(coerce_system_state_aliases(system))
        return {'success': True, 'message': 'simulated estop completed', 'simulated': True}

    async def start_task(self, *, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int) -> dict[str, Any]:
        self.ensure_available()
        if self.available and self._node is not None:
            return await self._node.call_start_task(task_type=task_type, target_selector=target_selector, place_profile=place_profile, auto_retry=auto_retry, max_retry=max_retry)
        return {'accepted': False, 'task_id': '', 'message': 'task execution requires authoritative ROS runtime readiness', 'simulated': True}

    async def command_gripper(self, *, open_gripper: bool) -> None:
        self.ensure_available()
        if self.available and self._node is not None:
            self._node.publish_hardware_command({'kind': 'OPEN_GRIPPER' if open_gripper else 'CLOSE_GRIPPER', 'task_id': 'manual', 'timeout_sec': 0.6})
            return
        self.state.set_gripper_open(open_gripper)

    async def jog_joint(self, *, joint_index: int, direction: int, step_deg: float) -> None:
        self.ensure_available()
        if self.available and self._node is not None:
            self._node.publish_hardware_command({'kind': 'JOG_JOINT', 'task_id': 'manual', 'jointIndex': int(joint_index), 'direction': 1 if int(direction) >= 0 else -1, 'stepDeg': float(step_deg), 'timeout_sec': 0.4})
            return
        hardware = self.state.get_hardware()
        joints = list(hardware.get('joints', [0.0] * 6))
        joints[joint_index] = round(joints[joint_index] + direction * step_deg, 3)
        hardware['joints'] = joints
        hardware['poseName'] = f'joint_{joint_index}_jog'
        self.state.set_hardware(hardware)

    async def servo_cartesian(self, *, axis: str, delta: float) -> None:
        """Send a cartesian servo command through the hardware bridge.

        Args:
            axis: Cartesian axis name.
            delta: Requested step size in meters or radians depending on axis.

        Raises:
            RosBridgeError: Raised when the command cannot be published.
        """
        self.ensure_available()
        if self.available and self._node is not None:
            self._node.publish_hardware_command({'kind': 'SERVO_CARTESIAN', 'task_id': 'manual', 'axis': str(axis), 'delta': float(delta), 'timeout_sec': 0.4})
            return
        hardware = self.state.get_hardware()
        raw_status = dict(hardware.get('rawStatus', {}))
        raw_status['servoCartesian'] = {'axis': str(axis), 'delta': float(delta), 'appliedAt': now_iso()}
        hardware['rawStatus'] = raw_status
        hardware['poseName'] = f"servo_{axis}"
        self.state.set_hardware(hardware)

    async def activate_calibration(self, *, profile_id: str) -> dict[str, Any]:
        """Activate the current calibration profile inside the ROS runtime.

        Args:
            profile_id: Logical profile identifier selected by the gateway/storage layer.

        Returns:
            dict[str, Any]: Activation result payload.

        Raises:
            Does not raise directly. When the ROS runtime is unavailable the method
            returns a failure payload so callers can roll back any optimistic local
            state changes instead of fabricating a successful activation.
        """
        if self.available and self._node is not None:
            return await self._node.call_activate_calibration(profile_id=profile_id)
        return {
            'success': False,
            'message': 'calibration activation requires ROS runtime connectivity',
            'profile_id': profile_id,
        }

    async def set_mode(self, *, mode: str) -> None:
        self.ensure_available()
        if self.available and self._node is not None:
            await self._node.call_set_mode(mode)
        system = self.state.get_system()
        system['controllerMode'] = mode
        if mode in {'manual', 'maintenance'}:
            system['runtimePhase'] = 'idle'
        self.state.set_system(coerce_system_state_aliases(system))

    async def reload_calibration(self) -> None:
        self.ensure_available()
        if self.available and self._node is not None:
            await self._node.call_reload_calibration()


if RCLPY_AVAILABLE:
    class GatewayRosNode(Node):
        def __init__(self, state: GatewayState, publisher: RuntimeEventPublisher) -> None:
            super().__init__('arm_hmi_gateway_node')
            self._state = state
            self._publisher = publisher
            self._hardware_cmd_pub = self.create_publisher(String, TopicNames.INTERNAL_HARDWARE_CMD, 20)
            self._home_client = self.create_client(HomeArm, ServiceNames.HOME)
            self._reset_fault_client = self.create_client(ResetFault, ServiceNames.RESET_FAULT)
            self._stop_client = self.create_client(StopTask, ServiceNames.STOP)
            self._stop_task_client = self.create_client(StopTask, ServiceNames.STOP_TASK)
            self._set_mode_client = self.create_client(SetMode, ServiceNames.SET_MODE)
            self._start_task_client = self.create_client(StartTask, ServiceNames.START_TASK)
            self._reload_calibration_client = self.create_client(Trigger, ServiceNames.CALIBRATION_MANAGER_RELOAD)
            self._activate_calibration_client = self.create_client(ActivateCalibrationVersion, ServiceNames.ACTIVATE_CALIBRATION) if ActivateCalibrationVersion is not object else None
            self._pick_place_action_client = ActionClient(self, PickPlaceTask, ActionNames.PICK_PLACE_TASK) if ActionClient is not object and PickPlaceTask is not object else None
            self._homing_action_client = ActionClient(self, Homing, ActionNames.HOMING) if ActionClient is not object and Homing is not object else None
            self._recover_action_client = ActionClient(self, Recover, ActionNames.RECOVER) if ActionClient is not object and Recover is not object else None
            self.String = String
            self.SystemState = SystemState
            self.HardwareState = HardwareState
            self.TargetInfo = TargetInfo
            self.TargetArray = TargetArray
            self.TaskEvent = TaskEvent
            self.TaskStatus = TaskStatus
            self.DiagnosticsSummary = DiagnosticsSummary
            self.CalibrationProfileMsg = CalibrationProfileMsg
            self.ReadinessState = ReadinessState
            self.TopicNames = TopicNames
            bind_runtime_ingress(self)
            self.create_timer(1.0, self._maintenance_tick)

        def publish_hardware_command(self, payload: dict[str, Any]) -> None:
            self._hardware_cmd_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

        async def call_home(self) -> dict[str, Any]:
            if self._homing_action_client is not None and self._homing_action_client.wait_for_server(timeout_sec=0.1):
                goal = Homing.Goal()
                goal.reason = 'gateway_home'
                accepted, result = await self._send_action_goal(self._homing_action_client, goal, wait_for_result=True)
                if accepted:
                    return {'success': bool(getattr(result, 'success', True)), 'message': str(getattr(result, 'message', 'home completed'))}
                return {'success': False, 'message': 'home action rejected'}
            request = HomeArm.Request()
            response = await self._call_service(self._home_client, request)
            return {'success': bool(response.success), 'message': str(response.message)}

        async def call_recover(self) -> dict[str, Any]:
            if self._recover_action_client is not None and self._recover_action_client.wait_for_server(timeout_sec=0.1):
                goal = Recover.Goal()
                goal.reason = 'gateway_recover'
                accepted, result = await self._send_action_goal(self._recover_action_client, goal, wait_for_result=True)
                if accepted:
                    return {'success': bool(getattr(result, 'success', True)), 'message': str(getattr(result, 'message', 'recover completed'))}
                return {'success': False, 'message': 'recover action rejected'}
            request = ResetFault.Request()
            response = await self._call_service(self._reset_fault_client, request)
            return {'success': bool(response.success), 'message': str(response.message)}

        async def call_reset_fault(self) -> dict[str, Any]:
            request = ResetFault.Request()
            response = await self._call_service(self._reset_fault_client, request)
            return {'success': bool(response.success), 'message': str(response.message)}

        async def call_stop_task(self) -> dict[str, Any]:
            request = StopTask.Request()
            client = self._stop_client if self._stop_client.wait_for_service(timeout_sec=0.1) else self._stop_task_client
            response = await self._call_service(client, request)
            return {'success': bool(response.success), 'message': str(response.message)}

        async def call_set_mode(self, mode: str) -> dict[str, Any]:
            request = SetMode.Request()
            request.mode = str(mode)
            response = await self._call_service(self._set_mode_client, request)
            return {'success': bool(response.success), 'message': str(response.message)}

        async def call_start_task(self, *, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int) -> dict[str, Any]:
            task_id = f"gw-{(target_selector or task_type or 'task').replace(' ', '-')[:12]}"
            if should_route_task_via_pick_place_action(task_type) and self._pick_place_action_client is not None and self._pick_place_action_client.wait_for_server(timeout_sec=0.1):
                goal = PickPlaceTask.Goal()
                payload = build_pick_place_action_goal_payload(task_id=task_id, target_selector=target_selector, place_profile=place_profile, max_retry=max_retry)
                goal.task_id = payload['task_id']
                goal.target_type = payload['target_type']
                goal.target_id = payload['target_id']
                goal.target_x = payload['target_x']
                goal.target_y = payload['target_y']
                goal.target_yaw = payload['target_yaw']
                goal.place_profile = payload['place_profile']
                goal.max_retry = payload['max_retry']
                accepted, _ = await self._send_action_goal(self._pick_place_action_client, goal, wait_for_result=False)
                return {'accepted': bool(accepted), 'task_id': task_id if accepted else '', 'message': 'action goal accepted' if accepted else 'action goal rejected'}
            request = StartTask.Request()
            request.task_type = str(task_type)
            request.target_selector = str(target_selector)
            request.place_profile = str(place_profile)
            request.auto_retry = bool(auto_retry)
            request.max_retry = int(max_retry)
            response = await self._call_service(self._start_task_client, request)
            return {'accepted': bool(response.accepted), 'task_id': str(response.task_id), 'message': str(response.message)}

        async def call_reload_calibration(self) -> None:
            request = Trigger.Request()
            await self._call_service(self._reload_calibration_client, request)

        async def call_activate_calibration(self, *, profile_id: str) -> dict[str, Any]:
            if self._activate_calibration_client is None:
                return {'success': False, 'message': 'activate calibration service unavailable', 'profile_id': profile_id}
            request = ActivateCalibrationVersion.Request()
            request.profile_id = str(profile_id)
            response = await self._call_service(self._activate_calibration_client, request)
            return {
                'success': bool(response.success),
                'message': str(response.message),
                'profile_id': str(getattr(response, 'profile_id', profile_id)),
            }

        async def _call_service(self, client, request, timeout_sec: float = 3.0):
            if not client.wait_for_service(timeout_sec=timeout_sec):
                raise RosBridgeError(f'ROS2 service unavailable: {client.srv_name}')
            return await resolve_ros_service_call(client, request, timeout_sec=timeout_sec)

        async def _send_action_goal(self, client, goal, *, wait_for_result: bool) -> tuple[bool, Any]:
            return await send_ros_action_goal(client, goal, wait_for_result=wait_for_result)

        def _maintenance_tick(self) -> None:
            self._state.prune_targets()
            self._publisher.publish_topics_threadsafe('targets', 'system', 'hardware', 'task', 'readiness', 'diagnostics')

        def _on_system_state(self, msg: SystemState) -> None:
            payload = map_system_state_message(msg, ros_connected=True, hardware_state=self._state.get_hardware())
            self._state.set_system(payload)
            task_payload = self._state.sync_task_from_system(payload)
            self._publisher.publish_topics_threadsafe('system', 'task', 'readiness', 'diagnostics')

        def _on_hardware_state(self, msg: HardwareState) -> None:
            payload = map_hardware_state_message(msg, gripper_open=self._state.get_last_gripper_open())
            self._state.set_hardware(payload)
            system_payload = self._state.get_system()
            system_payload['stm32Connected'] = bool(payload.get('sourceStm32Online', False))
            system_payload['esp32Connected'] = bool(payload.get('sourceEsp32Online', False))
            system_payload['cameraConnected'] = bool(payload.get('sourceCameraFrameIngressLive', False))
            self._state.set_system(system_payload)
            self._publisher.publish_topics_threadsafe('hardware', 'system', 'readiness', 'diagnostics')

        def _on_target(self, msg: TargetInfo) -> None:
            payload = map_target_message(msg)
            self._state.upsert_target(payload)
            self._publisher.publish_topics_threadsafe('targets', 'readiness', 'diagnostics')

        def _apply_targets_payload(self, payload: dict[str, Any]) -> None:
            apply_targets_payload(self._state, self._publisher, payload)

        def _on_targets_summary(self, msg: String) -> None:
            self._apply_targets_payload(decode_target_array_message(msg))

        def _on_targets_summary_typed(self, msg: TargetArray) -> None:
            self._apply_targets_payload(decode_target_array_message(msg))

        def _on_camera_frame_summary(self, msg: String) -> None:
            try:
                payload = json.loads(msg.data) if msg.data else {}
            except Exception:
                return
            if not isinstance(payload, dict):
                return
            try:
                frame_payload = map_camera_frame_summary(payload)
            except Exception:
                return
            self._state.set_vision_frame(frame_payload)
            self._publisher.publish_topics_threadsafe('vision_frame')

        def _on_log_event(self, msg: TaskEvent) -> None:
            payload = map_log_event_message(msg)
            request_id, correlation_id, task_run_id = self._state.request_context(str(payload.get('taskId') or ''))
            payload['requestId'] = payload.get('requestId') or request_id
            payload['correlationId'] = payload.get('correlationId') or correlation_id
            payload['taskRunId'] = payload.get('taskRunId') or task_run_id
            stored = self._state.append_log(payload)
            self._state.update_task_from_log(stored)
            self._publisher.publish_topics_threadsafe('diagnostics', extra_events=[('log.event.created', stored)])

        def _apply_task_status_payload(self, payload: dict[str, Any]) -> None:
            apply_task_status_payload(self._state, self._publisher, payload)

        def _on_task_status(self, msg: String) -> None:
            payload = decode_task_status_message(msg)
            if not payload:
                return
            self._apply_task_status_payload(payload)

        def _on_task_status_typed(self, msg: TaskStatus) -> None:
            payload = decode_task_status_message(msg)
            if not payload:
                return
            self._apply_task_status_payload(payload)

        def _apply_diagnostics_payload(self, payload: dict[str, Any]) -> None:
            apply_diagnostics_payload(self._state, self._publisher, payload)

        def _on_diagnostics_health(self, msg: String) -> None:
            payload = decode_diagnostics_summary_message(msg)
            if not payload:
                return
            self._apply_diagnostics_payload(payload)

        def _on_diagnostics_summary_typed(self, msg: DiagnosticsSummary) -> None:
            payload = decode_diagnostics_summary_message(msg)
            if not payload:
                return
            self._apply_diagnostics_payload(payload)

        def _apply_calibration_payload(self, payload: dict[str, Any]) -> None:
            apply_calibration_payload(self._state, self._publisher, payload)

        def _on_calibration_profile(self, msg: String) -> None:
            payload = decode_calibration_profile_message(msg)
            if not payload:
                return
            self._apply_calibration_payload(payload)

        def _on_calibration_profile_typed(self, msg: CalibrationProfileMsg) -> None:
            payload = decode_calibration_profile_message(msg)
            if not payload:
                return
            self._apply_calibration_payload(payload)

        def _apply_readiness_payload(self, payload: dict[str, Any]) -> None:
            apply_readiness_payload(self._state, self._publisher, payload)

        def _on_readiness_state(self, msg: String) -> None:
            """Consume the backend-published readiness snapshot."""
            payload = decode_readiness_message(msg)
            if not payload:
                return
            self._apply_readiness_payload(payload)

        def _on_readiness_state_typed(self, msg: ReadinessState) -> None:
            payload = decode_readiness_message(msg)
            if not payload:
                return
            self._apply_readiness_payload(payload)
