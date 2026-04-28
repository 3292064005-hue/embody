from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any

from .models import build_command_summary, new_request_id, coerce_system_state_aliases, default_readiness, map_camera_frame_summary, map_hardware_state_message, map_log_event_message, map_system_state_message, map_target_message, now_iso
from .runtime_bootstrap import local_preview_snapshot
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
from .command_contracts import execution_bound_for_command_plane, producer_for_command_plane, receipt_class_for_command_plane, runtime_interface_active_for_command_plane, runtime_interface_for_command_plane

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


class _BaseCommandExecutor:
    """Unified gateway-side execution backbone provider.

    Implementations own the concrete command semantics for one execution
    backbone while RosBridge remains the policy/audit surface.
    """

    backbone = 'unknown'

    def __init__(self, bridge: 'RosBridge') -> None:
        self._bridge = bridge

    async def home(self) -> dict[str, Any]:
        raise NotImplementedError

    async def reset_fault(self) -> dict[str, Any]:
        raise NotImplementedError

    async def recover(self) -> dict[str, Any]:
        raise NotImplementedError

    async def stop_task(self) -> dict[str, Any]:
        raise NotImplementedError

    async def emergency_stop(self) -> dict[str, Any]:
        raise NotImplementedError

    async def start_task(self, *, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def command_gripper(self, *, open_gripper: bool, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def jog_joint(self, *, joint_index: int, direction: int, step_deg: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def servo_cartesian(self, *, axis: str, delta: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def set_mode(self, *, mode: str) -> dict[str, Any]:
        raise NotImplementedError

    async def dispatch_runtime_command(self, *, command_plane: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError


class _AuthoritativeRosCommandExecutor(_BaseCommandExecutor):
    backbone = 'authoritative_transport'

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        result.setdefault('localPreviewOnly', False)
        result.setdefault('commandMode', self.backbone)
        result.setdefault('executionBackbone', 'ros_runtime')
        return result

    async def home(self) -> dict[str, Any]:
        return self._normalize(await self._bridge._node.call_home())

    async def reset_fault(self) -> dict[str, Any]:
        return self._normalize(await self._bridge._node.call_reset_fault())

    async def recover(self) -> dict[str, Any]:
        return self._normalize(await self._bridge._node.call_recover())

    async def stop_task(self) -> dict[str, Any]:
        return self._normalize(await self._bridge._node.call_stop_task())

    async def emergency_stop(self) -> dict[str, Any]:
        envelope = self._bridge._node.publish_hardware_command({'kind': 'ESTOP', 'task_id': 'system', 'timeout_sec': 0.2, 'producer': producer_for_command_plane('system_control'), 'command_plane': 'system_control', 'receipt_class': receipt_class_for_command_plane('system_control'), 'action': 'system.emergency_stop'})
        return self._normalize({'accepted': True, 'message': 'hardware estop accepted', 'commandId': envelope.get('command_id'), 'authoritativeStatus': 'transport_sent', 'completionPending': True})

    async def start_task(self, *, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        result = await self._bridge._node.call_start_task(task_type=task_type, target_selector=target_selector, place_profile=place_profile, auto_retry=auto_retry, max_retry=max_retry, trace=trace)
        result = dict(result)
        result.setdefault('executionBackbone', 'ros_runtime')
        return result

    async def command_gripper(self, *, open_gripper: bool, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        envelope = self._bridge._node.publish_hardware_command({**dict(trace or {}), 'kind': 'OPEN_GRIPPER' if open_gripper else 'CLOSE_GRIPPER', 'task_id': 'manual', 'timeout_sec': 0.6, 'producer': producer_for_command_plane('manual_control'), 'command_plane': 'manual_control', 'receipt_class': receipt_class_for_command_plane('manual_control'), 'action': 'hardware.gripper'})
        return self._normalize({'accepted': True, 'message': 'hardware gripper command accepted', 'open': bool(open_gripper), 'commandId': envelope.get('command_id'), 'authoritativeStatus': 'transport_sent', 'completionPending': True})

    async def jog_joint(self, *, joint_index: int, direction: int, step_deg: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        envelope = self._bridge._node.publish_hardware_command({**dict(trace or {}), 'kind': 'JOG_JOINT', 'task_id': 'manual', 'jointIndex': int(joint_index), 'direction': 1 if int(direction) >= 0 else -1, 'stepDeg': float(step_deg), 'timeout_sec': 0.4, 'producer': producer_for_command_plane('manual_control'), 'command_plane': 'manual_control', 'receipt_class': receipt_class_for_command_plane('manual_control'), 'action': 'hardware.jog_joint'})
        return self._normalize({'accepted': True, 'message': 'hardware joint jog command accepted', 'jointIndex': int(joint_index), 'direction': 1 if int(direction) >= 0 else -1, 'stepDeg': float(step_deg), 'commandId': envelope.get('command_id'), 'authoritativeStatus': 'transport_sent', 'completionPending': True})

    async def servo_cartesian(self, *, axis: str, delta: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        envelope = self._bridge._node.publish_hardware_command({**dict(trace or {}), 'kind': 'SERVO_CARTESIAN', 'task_id': 'manual', 'axis': str(axis), 'delta': float(delta), 'timeout_sec': 0.4, 'producer': producer_for_command_plane('manual_control'), 'command_plane': 'manual_control', 'receipt_class': receipt_class_for_command_plane('manual_control'), 'action': 'hardware.servo_cartesian'})
        return self._normalize({'accepted': True, 'message': 'hardware cartesian servo command accepted', 'axis': str(axis), 'delta': float(delta), 'commandId': envelope.get('command_id'), 'authoritativeStatus': 'transport_sent', 'completionPending': True})

    async def set_mode(self, *, mode: str) -> dict[str, Any]:
        return self._normalize(await self._bridge._node.call_set_mode(mode))

    async def dispatch_runtime_command(self, *, command_plane: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        if action == 'task.start':
            return await self.start_task(
                task_type=str(payload.get('task_type', '') or ''),
                target_selector=str(payload.get('target_selector', '') or ''),
                place_profile=str(payload.get('place_profile', '') or ''),
                auto_retry=bool(payload.get('auto_retry', False)),
                max_retry=int(payload.get('max_retry', 0) or 0),
                trace=payload,
            )
        if action == 'task.stop':
            return await self.stop_task()
        if action == 'system.home':
            return await self.home()
        if action == 'system.reset_fault':
            return await self.reset_fault()
        if action == 'system.recover':
            return await self.recover()
        if action == 'system.emergency_stop':
            return await self.emergency_stop()
        if action == 'hardware.set_mode':
            return await self.set_mode(mode=str(payload.get('mode', '') or 'idle'))
        if action == 'hardware.gripper':
            return await self.command_gripper(open_gripper=bool(payload.get('open', False)), trace=payload)
        if action == 'hardware.jog_joint':
            return await self.jog_joint(
                joint_index=int(payload.get('jointIndex', 0) or 0),
                direction=int(payload.get('direction', 1) or 1),
                step_deg=float(payload.get('stepDeg', 0.0) or 0.0),
                trace=payload,
            )
        if action == 'hardware.servo_cartesian':
            return await self.servo_cartesian(
                axis=str(payload.get('axis', '') or ''),
                delta=float(payload.get('delta', 0.0) or 0.0),
                trace=payload,
            )
        raise RosBridgeError(f'unsupported runtime command dispatch for {command_plane}:{action}')


class _LocalPreviewCommandExecutor(_BaseCommandExecutor):
    backbone = 'local_preview_only'

    def _result(self, *, action: str, message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._bridge._local_preview_command_result(action=action, message=message, extra=extra)

    async def home(self) -> dict[str, Any]:
        hardware = self._bridge.state.get_hardware()
        hardware['homed'] = True
        hardware['busy'] = False
        self._bridge.state.set_hardware(hardware)
        return self._result(action='system.home', message='local preview home projection applied')

    async def reset_fault(self) -> dict[str, Any]:
        system = self._bridge.state.get_system()
        system['emergencyStop'] = False
        system['faultCode'] = None
        system['faultMessage'] = None
        system['runtimePhase'] = 'idle'
        system['controllerMode'] = 'idle'
        system['taskStage'] = 'done'
        self._bridge.state.set_system(coerce_system_state_aliases(system))
        return self._result(action='system.reset_fault', message='local preview reset-fault projection applied')

    async def recover(self) -> dict[str, Any]:
        system = self._bridge.state.get_system()
        system['emergencyStop'] = False
        system['faultCode'] = None
        system['faultMessage'] = None
        system['runtimePhase'] = 'idle'
        system['controllerMode'] = 'idle'
        system['taskStage'] = 'done'
        self._bridge.state.set_system(coerce_system_state_aliases(system))
        hardware = self._bridge.state.get_hardware()
        hardware['busy'] = False
        self._bridge.state.set_hardware(hardware)
        return self._result(action='system.recover', message='local preview recover projection applied')

    async def stop_task(self) -> dict[str, Any]:
        system = self._bridge.state.get_system()
        system['runtimePhase'] = 'safe_stop'
        system['controllerMode'] = 'maintenance'
        system['taskStage'] = 'failed'
        system['faultMessage'] = 'task stopped'
        self._bridge.state.set_system(coerce_system_state_aliases(system))
        return self._result(action='task.stop', message='local preview task-stop projection applied')

    async def emergency_stop(self) -> dict[str, Any]:
        system = self._bridge.state.get_system()
        system['runtimePhase'] = 'safe_stop'
        system['controllerMode'] = 'maintenance'
        system['taskStage'] = 'failed'
        system['emergencyStop'] = True
        system['faultCode'] = 'ESTOP'
        system['faultMessage'] = 'simulated estop'
        self._bridge.state.set_system(coerce_system_state_aliases(system))
        return self._result(action='system.emergency_stop', message='local preview emergency-stop projection applied')

    async def start_task(self, *, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        del task_type, target_selector, place_profile, auto_retry, max_retry, trace
        return {'accepted': False, 'task_id': '', 'message': 'task execution requires authoritative ROS runtime readiness', 'simulated': True, 'localPreviewOnly': True, 'commandMode': self.backbone, 'executionBackbone': 'local_preview'}

    async def command_gripper(self, *, open_gripper: bool, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        self._bridge.state.set_gripper_open(open_gripper)
        return self._result(action='hardware.gripper', message='local preview gripper projection applied', extra={'open': bool(open_gripper)})

    async def jog_joint(self, *, joint_index: int, direction: int, step_deg: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        hardware = self._bridge.state.get_hardware()
        joints = list(hardware.get('joints', [0.0] * 6))
        joints[joint_index] = round(joints[joint_index] + direction * step_deg, 3)
        hardware['joints'] = joints
        hardware['poseName'] = f'joint_{joint_index}_jog'
        self._bridge.state.set_hardware(hardware)
        return self._result(action='hardware.jog_joint', message='local preview joint jog projection applied', extra={'jointIndex': int(joint_index), 'direction': 1 if int(direction) >= 0 else -1, 'stepDeg': float(step_deg)})

    async def servo_cartesian(self, *, axis: str, delta: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        hardware = self._bridge.state.get_hardware()
        raw_status = dict(hardware.get('rawStatus', {}))
        raw_status['servoCartesian'] = {'axis': str(axis), 'delta': float(delta), 'appliedAt': now_iso()}
        hardware['rawStatus'] = raw_status
        hardware['poseName'] = f"servo_{axis}"
        self._bridge.state.set_hardware(hardware)
        return self._result(action='hardware.servo_cartesian', message='local preview cartesian servo projection applied', extra={'axis': str(axis), 'delta': float(delta)})

    async def set_mode(self, *, mode: str) -> dict[str, Any]:
        normalized = str(mode or 'idle').strip().lower()
        allowed_modes = {'idle', 'manual', 'maintenance'}
        if normalized not in allowed_modes:
            raise RosBridgeError('local preview mode switching only allows idle/manual/maintenance')
        system = self._bridge.state.get_system()
        system['controllerMode'] = normalized
        system['runtimePhase'] = 'idle'
        self._bridge.state.set_system(coerce_system_state_aliases(system))
        return self._result(action='set_mode', message=f'local preview controller mode set to {normalized}', extra={'mode': normalized})

    async def dispatch_runtime_command(self, *, command_plane: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        if action == 'task.start':
            return await self.start_task(
                task_type=str(payload.get('task_type', '') or ''),
                target_selector=str(payload.get('target_selector', '') or ''),
                place_profile=str(payload.get('place_profile', '') or ''),
                auto_retry=bool(payload.get('auto_retry', False)),
                max_retry=int(payload.get('max_retry', 0) or 0),
                trace=payload,
            )
        if action == 'task.stop':
            return await self.stop_task()
        if action == 'system.home':
            return await self.home()
        if action == 'system.reset_fault':
            return await self.reset_fault()
        if action == 'system.recover':
            return await self.recover()
        if action == 'system.emergency_stop':
            return await self.emergency_stop()
        if action == 'hardware.set_mode':
            return await self.set_mode(mode=str(payload.get('mode', '') or 'idle'))
        if action == 'hardware.gripper':
            return await self.command_gripper(open_gripper=bool(payload.get('open', False)), trace=payload)
        if action == 'hardware.jog_joint':
            return await self.jog_joint(
                joint_index=int(payload.get('jointIndex', 0) or 0),
                direction=int(payload.get('direction', 1) or 1),
                step_deg=float(payload.get('stepDeg', 0.0) or 0.0),
                trace=payload,
            )
        if action == 'hardware.servo_cartesian':
            return await self.servo_cartesian(
                axis=str(payload.get('axis', '') or ''),
                delta=float(payload.get('delta', 0.0) or 0.0),
                trace=payload,
            )
        raise RosBridgeError(f'unsupported runtime command dispatch for {command_plane}:{action}')


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
        self._release_profile = str(os.environ.get('EMBODIED_ARM_BUILD_PROFILE', os.environ.get('VITE_BUILD_PROFILE', 'development')) or 'development').strip().lower()
        self._allow_sim_fallback = os.environ.get('EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK', 'false').lower() == 'true'
        self._enable_local_preview_commands = os.environ.get('EMBODIED_ARM_ENABLE_LOCAL_PREVIEW_COMMANDS', 'false').lower() == 'true'
        self._local_preview_guard_reason = ''
        if self._runtime_profile != 'dev-hmi-mock' and (self._allow_sim_fallback or self._enable_local_preview_commands):
            self._local_preview_guard_reason = 'local preview commands are only supported in dev-hmi-mock runtime profile'
            self._allow_sim_fallback = False
            self._enable_local_preview_commands = False
        elif self._release_profile in {'release', 'production'} and (self._allow_sim_fallback or self._enable_local_preview_commands):
            self._local_preview_guard_reason = 'release build profile forbids simulation fallback and local preview commands'
            self._allow_sim_fallback = False
            self._enable_local_preview_commands = False
        self._simulated_runtime_active = False
        self._authoritative_executor: _AuthoritativeRosCommandExecutor | None = None
        self._local_preview_executor: _LocalPreviewCommandExecutor | None = None

    def _can_use_local_simulated_runtime(self) -> bool:
        return self._runtime_profile == 'dev-hmi-mock' and self._allow_sim_fallback and self._enable_local_preview_commands

    def _local_preview_command_result(self, *, action: str, message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            'accepted': True,
            'action': str(action),
            'message': str(message),
            'simulated': True,
            'localPreviewOnly': True,
            'commandMode': 'local_preview_only',
        }
        if extra:
            payload.update(extra)
        return payload

    def _build_simulated_readiness_snapshot(self) -> dict[str, Any]:
        return local_preview_snapshot()

    def start(self) -> None:
        if not self.available:
            system = self.state.get_system()
            system['rosConnected'] = False
            if self._can_use_local_simulated_runtime():
                self._simulated_runtime_active = True
                self.state.set_readiness_snapshot(self._build_simulated_readiness_snapshot(), authoritative=False)
                system['faultMessage'] = 'ROS2 bridge unavailable; gateway running in explicit dev-hmi-mock local preview profile.'
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
        guidance = 'ROS2 bridge unavailable. 请在已 source ROS2 与工作区环境后启动网关，或显式设置 EMBODIED_ARM_RUNTIME_PROFILE=dev-hmi-mock、EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK=true 与 EMBODIED_ARM_ENABLE_LOCAL_PREVIEW_COMMANDS=true（该组合仅投影本地 preview/maintenance 语义）。'
        if self._local_preview_guard_reason:
            guidance = f'{guidance} 当前已阻断 local preview：{self._local_preview_guard_reason}。'
        raise RosBridgeError(guidance)

    def _executor_or_raise(self) -> _BaseCommandExecutor:
        self.ensure_available()
        if self.available and self._node is not None:
            if self._authoritative_executor is None:
                self._authoritative_executor = _AuthoritativeRosCommandExecutor(self)
            return self._authoritative_executor
        if self._simulated_runtime_active:
            if self._local_preview_executor is None:
                self._local_preview_executor = _LocalPreviewCommandExecutor(self)
            return self._local_preview_executor
        raise RosBridgeError('no execution backbone available')

    async def home(self) -> dict[str, Any]:
        return await self._executor_or_raise().home()

    async def reset_fault(self) -> dict[str, Any]:
        return await self._executor_or_raise().reset_fault()


    async def recover(self) -> dict[str, Any]:
        return await self._executor_or_raise().recover()

    async def stop_task(self) -> dict[str, Any]:
        return await self._executor_or_raise().stop_task()

    async def emergency_stop(self) -> dict[str, Any]:
        return await self._executor_or_raise().emergency_stop()

    async def start_task(self, *, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._executor_or_raise().start_task(task_type=task_type, target_selector=target_selector, place_profile=place_profile, auto_retry=auto_retry, max_retry=max_retry, trace=trace)

    async def command_gripper(self, *, open_gripper: bool, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._executor_or_raise().command_gripper(open_gripper=open_gripper, trace=trace)

    async def jog_joint(self, *, joint_index: int, direction: int, step_deg: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._executor_or_raise().jog_joint(joint_index=joint_index, direction=direction, step_deg=step_deg, trace=trace)

    async def servo_cartesian(self, *, axis: str, delta: float, trace: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a cartesian servo command through the selected execution backbone.

        Args:
            axis: Cartesian axis name.
            delta: Requested step size in meters or radians depending on axis.

        Raises:
            RosBridgeError: Raised when no execution backbone is available.
        """
        return await self._executor_or_raise().servo_cartesian(axis=axis, delta=delta, trace=trace)

    async def dispatch_runtime_command(self, *, command_plane: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch one public runtime command through the unified gateway ingress.

        Args:
            command_plane: Authoritative command-plane key.
            action: Stable gateway action name.
            payload: Transport payload consumed by the selected execution backbone.

        Returns:
            dict[str, Any]: Transport result payload.

        Raises:
            RosBridgeError: Raised when no execution backbone is available or the
                action is unsupported by the selected backbone.

        Boundary behavior:
            The unified ingress keeps task/manual/system commands on one gateway
            runtime entrypoint while still allowing the selected backend to fan
            out to the correct runtime transport underneath.
        """
        return await self._executor_or_raise().dispatch_runtime_command(command_plane=command_plane, action=action, payload=payload)

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

    async def set_mode(self, *, mode: str) -> dict[str, Any]:
        return await self._executor_or_raise().set_mode(mode=mode)

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
            self._voice_event_seq = 0
            self._pending_hardware_commands: dict[str, dict[str, Any]] = {}
            bind_runtime_ingress(self)
            self.create_timer(1.0, self._maintenance_tick)

        def publish_hardware_command(self, payload: dict[str, Any]) -> dict[str, Any]:
            """Publish one hardware command envelope and retain its receipt context.

            Args:
                payload: Normalized command payload. Callers may include
                    request/correlation ids, action, command plane, and operator role.

            Returns:
                dict[str, Any]: The exact envelope published to ROS. It always
                    contains a stable ``command_id`` for feedback correlation.

            Raises:
                Does not raise directly; publisher exceptions propagate from ROS.

            Boundary behavior:
                Missing command metadata is filled from the command-plane contract.
                The pending context is best-effort and feedback without a matching
                command id is still recorded as an observed hardware receipt.
            """
            envelope = dict(payload)
            command_plane = str(envelope.get('command_plane', 'manual_control') or 'manual_control')
            envelope.setdefault('producer', producer_for_command_plane(command_plane))
            envelope.setdefault('command_plane', command_plane)
            envelope.setdefault('receipt_class', receipt_class_for_command_plane(command_plane))
            envelope.setdefault('command_id', new_request_id('cmd'))
            envelope.setdefault('request_id', str(envelope.get('requestId', '') or envelope.get('request_id', '') or new_request_id('hw')))
            envelope.setdefault('correlation_id', str(envelope.get('correlationId', '') or envelope.get('correlation_id', '') or ''))
            envelope.setdefault('task_run_id', str(envelope.get('taskRunId', '') or envelope.get('task_run_id', '') or ''))
            envelope.setdefault('episode_id', str(envelope.get('episodeId', '') or envelope.get('episode_id', '') or envelope.get('task_run_id', '') or ''))
            envelope.setdefault('action', str(envelope.get('action', 'hardware.command') or 'hardware.command'))
            self._pending_hardware_commands[str(envelope['command_id'])] = {
                'action': str(envelope.get('action', 'hardware.command') or 'hardware.command'),
                'requestId': str(envelope.get('request_id', '') or ''),
                'correlationId': str(envelope.get('correlation_id', '') or ''),
                'taskRunId': str(envelope.get('task_run_id', '') or ''),
                'episodeId': str(envelope.get('episode_id', '') or ''),
                'taskId': str(envelope.get('task_id', '') or ''),
                'commandPlane': command_plane,
                'receiptClass': str(envelope.get('receipt_class', receipt_class_for_command_plane(command_plane)) or receipt_class_for_command_plane(command_plane)),
                'role': str(envelope.get('role', 'system') or 'system'),
                'payload': dict(envelope),
            }
            self._hardware_cmd_pub.publish(String(data=json.dumps(envelope, ensure_ascii=False)))
            return envelope

        @staticmethod
        def _hardware_feedback_receipt_status(status: str) -> tuple[str, bool]:
            """Map dispatcher feedback into public command-receipt lifecycle states.

            Args:
                status: Raw dispatcher feedback status, for example sent/ack/nack/done/timeout.

            Returns:
                tuple[str, bool]: Normalized receipt status and whether the status
                    is terminal for the pending command correlation entry.

            Raises:
                Does not raise. Unknown statuses degrade to observed/non-terminal.
            """
            normalized = str(status or '').strip().lower()
            mapping = {
                'sent': ('transport_sent', False),
                'ack': ('acked', False),
                'accepted': ('acked', False),
                'retry': ('retry', False),
                'done': ('completed', True),
                'soft_done': ('completed', True),
                'nack': ('rejected', True),
                'failed': ('rejected', True),
                'fault': ('rejected', True),
                'timeout': ('timeout', True),
                'canceled': ('canceled', True),
            }
            return mapping.get(normalized, ('observed', False))

        def _on_hardware_feedback(self, msg: String) -> None:
            """Consume dispatcher feedback and append correlated command receipts.

            Args:
                msg: JSON string published on ``TopicNames.HARDWARE_FEEDBACK``.

            Returns:
                None. Receipts are appended and websocket diagnostics are published
                on a best-effort basis.

            Raises:
                Does not raise. Malformed payloads are ignored to keep the ROS
                subscription thread alive.

            Boundary behavior:
                Feedback without a known command id is still recorded with a new
                ingress request id, so diagnostics do not silently drop hardware
                terminal events.
            """
            raw = str(getattr(msg, 'data', '') or '')
            try:
                payload = json.loads(raw) if raw else {}
            except Exception:
                payload = {'status': 'decode_failed', 'message': raw}
            if not isinstance(payload, dict):
                payload = {'status': 'invalid_payload', 'payload': payload}
            command_id = str(payload.get('command_id', payload.get('commandId', '')) or '')
            pending = self._pending_hardware_commands.get(command_id, {}) if command_id else {}
            receipt_status, terminal = self._hardware_feedback_receipt_status(str(payload.get('status', '')))
            command_plane = str(payload.get('command_plane', payload.get('commandPlane', pending.get('commandPlane', 'manual_control'))) or 'manual_control')
            receipt_class = str(payload.get('receipt_class', payload.get('receiptClass', pending.get('receiptClass', receipt_class_for_command_plane(command_plane)))) or receipt_class_for_command_plane(command_plane))
            action = str(payload.get('action', pending.get('action', 'hardware.feedback')) or 'hardware.feedback')
            request_id = str(payload.get('request_id', payload.get('requestId', pending.get('requestId', ''))) or '') or new_request_id('hwfb')
            correlation_id = str(payload.get('correlation_id', payload.get('correlationId', pending.get('correlationId', ''))) or '') or None
            task_run_id = str(payload.get('task_run_id', payload.get('taskRunId', pending.get('taskRunId', ''))) or '') or None
            episode_id = str(payload.get('episode_id', payload.get('episodeId', pending.get('episodeId', ''))) or '') or task_run_id
            task_id = str(payload.get('task_id', payload.get('taskId', pending.get('taskId', ''))) or '') or None
            message = str(payload.get('message', payload.get('result', payload.get('status', 'hardware feedback received'))) or 'hardware feedback received')
            receipt = self._state.append_command_receipt({
                'id': new_request_id('receipt'),
                'timestamp': now_iso(),
                'action': action,
                'status': receipt_status,
                'role': str(pending.get('role', 'system') or 'system'),
                'requestId': request_id,
                'correlationId': correlation_id,
                'commandPlane': command_plane,
                'receiptClass': receipt_class,
                'executionBound': bool(execution_bound_for_command_plane(command_plane)),
                'errorCode': str(payload.get('errorCode', payload.get('error_code', '')) or '') or None,
                'operatorActionable': receipt_status in {'rejected', 'timeout', 'canceled'},
                'message': message,
                'payload': {**dict(payload), 'commandId': command_id, 'terminal': terminal},
                'traceEnvelope': {
                    'requestId': request_id,
                    'correlationId': correlation_id,
                    'taskId': task_id,
                    'taskRunId': task_run_id,
                    'episodeId': episode_id,
                    'errorCode': str(payload.get('errorCode', payload.get('error_code', '')) or '') or None,
                    'operatorActionable': receipt_status in {'rejected', 'timeout', 'canceled'},
                },
            })
            if command_id and terminal:
                self._pending_hardware_commands.pop(command_id, None)
            try:
                self._publisher.publish_topics_threadsafe('diagnostics', extra_events=[('command.receipt.created', receipt)])
            except Exception:
                pass

        def _runtime_ingress_active(self, command_plane: str) -> bool:
            return runtime_interface_active_for_command_plane(command_plane)

        def _record_ingress_blocked(self, *, command_plane: str, action: str, payload: dict[str, Any], message: str, module: str, event: str, audit_required: bool = True) -> None:
            runtime_interface = runtime_interface_for_command_plane(command_plane)
            stored = self._state.append_log({
                'id': new_request_id('log'),
                'timestamp': now_iso(),
                'level': 'warn',
                'module': module,
                'taskId': None,
                'requestId': new_request_id('ingress'),
                'correlationId': None,
                'event': event,
                'message': str(message),
                'payload': {**dict(payload), 'runtimeInterface': runtime_interface, 'commandPlane': command_plane},
                'operatorActionable': False,
            })
            extra_events: list[tuple[str, Any]] = [('log.event.created', stored)]
            if audit_required:
                audit = self._state.append_audit({
                    'id': new_request_id('audit'),
                    'timestamp': now_iso(),
                    'action': action,
                    'status': 'blocked',
                    'role': 'system',
                    'requestId': stored['requestId'],
                    'correlationId': None,
                    'errorCode': 'contract_violation',
                    'operatorActionable': False,
                    'message': str(message),
                    'payload': {**dict(payload), 'runtimeInterface': runtime_interface, 'commandPlane': command_plane},
                })
                extra_events.append(('audit.event.created', audit))
            receipt = self._state.append_command_receipt({
                'id': new_request_id('receipt'),
                'timestamp': now_iso(),
                'action': action,
                'status': 'blocked',
                'role': 'system',
                'requestId': stored['requestId'],
                'correlationId': None,
                'commandPlane': command_plane,
                'receiptClass': receipt_class_for_command_plane(command_plane),
                'executionBound': bool(execution_bound_for_command_plane(command_plane)),
                'errorCode': 'contract_violation',
                'operatorActionable': False,
                'message': str(message),
                'payload': {**dict(payload), 'runtimeInterface': runtime_interface, 'commandPlane': command_plane},
            })
            extra_events.append(('command.receipt.created', receipt))
            self._publisher.publish_topics_threadsafe('diagnostics', extra_events=extra_events)

        async def call_home(self) -> dict[str, Any]:
            if self._homing_action_client is not None and self._homing_action_client.wait_for_server(timeout_sec=0.1):
                goal = Homing.Goal()
                goal.reason = 'gateway_home'
                accepted, result = await self._send_action_goal(self._homing_action_client, goal, wait_for_result=True)
                if accepted:
                    if not bool(getattr(result, 'success', True)):
                        raise RosBridgeError(str(getattr(result, 'message', 'home action failed')))
                    return {'accepted': True, 'message': str(getattr(result, 'message', 'home command accepted'))}
                raise RosBridgeError('home action rejected')
            request = HomeArm.Request()
            response = await self._call_service(self._home_client, request)
            if not bool(response.success):
                raise RosBridgeError(str(response.message or 'home command rejected'))
            return {'accepted': True, 'message': str(response.message or 'home command accepted')}

        async def call_recover(self) -> dict[str, Any]:
            if self._recover_action_client is not None and self._recover_action_client.wait_for_server(timeout_sec=0.1):
                goal = Recover.Goal()
                goal.reason = 'gateway_recover'
                accepted, result = await self._send_action_goal(self._recover_action_client, goal, wait_for_result=True)
                if accepted:
                    if not bool(getattr(result, 'success', True)):
                        raise RosBridgeError(str(getattr(result, 'message', 'recover action failed')))
                    return {'accepted': True, 'message': str(getattr(result, 'message', 'recover command accepted'))}
                raise RosBridgeError('recover action rejected')
            request = ResetFault.Request()
            response = await self._call_service(self._reset_fault_client, request)
            if not bool(response.success):
                raise RosBridgeError(str(response.message or 'recover command rejected'))
            return {'accepted': True, 'message': str(response.message or 'recover command accepted')}

        async def call_reset_fault(self) -> dict[str, Any]:
            request = ResetFault.Request()
            response = await self._call_service(self._reset_fault_client, request)
            if not bool(response.success):
                raise RosBridgeError(str(response.message or 'reset-fault command rejected'))
            return {'accepted': True, 'message': str(response.message or 'reset-fault command accepted')}

        async def call_stop_task(self) -> dict[str, Any]:
            request = StopTask.Request()
            client = self._stop_client if self._stop_client.wait_for_service(timeout_sec=0.1) else self._stop_task_client
            response = await self._call_service(client, request)
            if not bool(response.success):
                raise RosBridgeError(str(response.message or 'stop-task command rejected'))
            return {'accepted': True, 'message': str(response.message or 'stop-task command accepted')}

        async def call_set_mode(self, mode: str) -> dict[str, Any]:
            request = SetMode.Request()
            request.mode = str(mode)
            response = await self._call_service(self._set_mode_client, request)
            if not bool(response.success):
                raise RosBridgeError(str(response.message or 'set-mode command rejected'))
            return {'accepted': True, 'message': str(response.message or 'set-mode command accepted'), 'mode': str(mode)}

        async def call_start_task(self, *, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int, trace: dict[str, Any] | None = None) -> dict[str, Any]:
            """Call the backend task runtime while preserving Gateway trace identity.

            Args:
                task_type: Backend task type.
                target_selector: Target selector/category forwarded to the backend.
                place_profile: Placement profile name.
                auto_retry: Whether automatic retry is enabled.
                max_retry: Retry budget.
                trace: Gateway command payload containing request/correlation ids,
                    task-run ids, template id, graph key, and runtime tier.

            Returns:
                dict[str, Any]: Backend acceptance payload with the original trace
                identifiers mirrored for REST receipts and websocket projections.

            Raises:
                RosBridgeError: Propagated from service/action failures.

            Boundary behavior:
                New trace fields are set only when present on generated ROS
                request/action classes, so old overlays fail closed by backend
                fallback identifiers rather than crashing the gateway.
            """
            trace = dict(trace or {})
            task_id = f"gw-{(target_selector or task_type or 'task').replace(' ', '-')[:12]}"
            request_id = str(trace.get('request_id', trace.get('requestId', '')) or '')
            correlation_id = str(trace.get('correlation_id', trace.get('correlationId', '')) or '')
            task_run_id = str(trace.get('task_run_id', trace.get('taskRunId', '')) or '')
            episode_id = str(trace.get('episode_id', trace.get('episodeId', task_run_id)) or task_run_id)
            template_id = str(trace.get('template_id', trace.get('templateId', '')) or '')
            graph_key = str(trace.get('graph_key', trace.get('graphKey', '')) or '')
            runtime_tier = str(trace.get('runtime_tier', trace.get('runtimeTier', '')) or '')
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
                for field_name, value in {
                    'request_id': request_id,
                    'correlation_id': correlation_id,
                    'task_run_id': task_run_id,
                    'episode_id': episode_id,
                    'template_id': template_id,
                    'graph_key': graph_key,
                    'runtime_tier': runtime_tier,
                }.items():
                    if hasattr(goal, field_name):
                        setattr(goal, field_name, str(value))
                accepted, _ = await self._send_action_goal(self._pick_place_action_client, goal, wait_for_result=False)
                return {'accepted': bool(accepted), 'task_id': task_id if accepted else '', 'message': 'action goal accepted' if accepted else 'action goal rejected', 'requestId': request_id, 'correlationId': correlation_id, 'taskRunId': task_run_id, 'episodeId': episode_id}
            request = StartTask.Request()
            request.task_type = str(task_type)
            request.target_selector = str(target_selector)
            request.place_profile = str(place_profile)
            request.auto_retry = bool(auto_retry)
            request.max_retry = int(max_retry)
            for field_name, value in {
                'request_id': request_id,
                'correlation_id': correlation_id,
                'task_run_id': task_run_id,
                'episode_id': episode_id,
                'template_id': template_id,
                'graph_key': graph_key,
                'runtime_tier': runtime_tier,
            }.items():
                if hasattr(request, field_name):
                    setattr(request, field_name, str(value))
            response = await self._call_service(self._start_task_client, request)
            return {'accepted': bool(response.accepted), 'task_id': str(response.task_id), 'message': str(response.message), 'requestId': request_id, 'correlationId': correlation_id, 'taskRunId': task_run_id, 'episodeId': episode_id}

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
            if not self._runtime_ingress_active('vision_observability'):
                self._record_ingress_blocked(command_plane='vision_observability', action='vision.ingress', payload=payload, message='runtime interface vision_event_ingress is not active', module='vision.gateway', event='vision.ingress.blocked', audit_required=False)
                return
            self._state.upsert_target(payload)
            self._publisher.publish_topics_threadsafe('targets', 'readiness', 'diagnostics')

        def _apply_targets_payload(self, payload: dict[str, Any]) -> None:
            if not self._runtime_ingress_active('vision_observability'):
                self._record_ingress_blocked(command_plane='vision_observability', action='vision.ingress', payload=payload, message='runtime interface vision_event_ingress is not active', module='vision.gateway', event='vision.ingress.blocked', audit_required=False)
                return
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
            if not self._runtime_ingress_active('vision_observability'):
                self._record_ingress_blocked(command_plane='vision_observability', action='vision.frame', payload=payload, message='runtime interface vision_event_ingress is not active', module='vision.gateway', event='vision.frame.blocked', audit_required=False)
                return
            try:
                frame_payload = map_camera_frame_summary(payload)
            except Exception:
                return
            self._state.set_vision_frame(frame_payload)
            self._publisher.publish_topics_threadsafe('vision_frame')

        def _on_voice_events(self, msg: String) -> None:
            """Consume ESP32 voice-event payloads into the gateway observability stream.

            Args:
                msg: JSON string published by the ESP32 gateway on
                    ``TopicNames.VOICE_EVENTS``.

            Returns:
                None. Parsed events are appended to the log stream and mirrored
                into the audit stream so HMI operators can trace voice-originated
                triggers through the same observability surfaces as manual commands.

            Boundary behavior:
                Malformed payloads do not raise; they are converted into one warn
                log entry tagged ``voice.event.decode_failed``.
            """
            raw_text = str(getattr(msg, 'data', '') or '')
            try:
                payload = json.loads(raw_text) if raw_text else {}
            except Exception:
                payload = {'status': 'decode_failed', 'message': raw_text}
            if not isinstance(payload, dict):
                payload = {'status': 'invalid_payload', 'payload': payload}
            payload = {
                **dict(payload),
                'telemetryOnly': bool(payload.get('telemetryOnly', True)),
                'actionExecutionBound': bool(payload.get('actionExecutionBound', False)),
                'routing': str(payload.get('routing', 'observability_only') or 'observability_only'),
            }
            if not self._runtime_ingress_active('voice_observability'):
                self._record_ingress_blocked(command_plane='voice_observability', action='voice.event', payload=payload, message='runtime interface voice_event_ingress is not active', module='voice.gateway', event='voice.event.blocked')
                return
            request_id = str(payload.get('requestId', '')) or None
            correlation_id = str(payload.get('correlationId', '')) or None
            task_run_id = str(payload.get('taskRunId', '')) or None
            episode_id = str(payload.get('episodeId', '')) or None
            task_id = str(payload.get('taskId', '')) or None
            if task_id:
                ctx_payload = self._state.request_context_payload(task_id) or {}
                request_id = request_id or str(ctx_payload.get('requestId', '') or '') or None
                correlation_id = correlation_id or str(ctx_payload.get('correlationId', '') or '') or None
                task_run_id = task_run_id or str(ctx_payload.get('taskRunId', '') or '') or None
                episode_id = episode_id or str(ctx_payload.get('episodeId', '') or '') or None
            event_name = str(payload.get('event', payload.get('status', 'voice_event')) or 'voice_event')
            level = str(payload.get('level', 'info') or 'info').lower()
            if level not in {'info', 'warn', 'error', 'fault'}:
                level = 'info'
            self._voice_event_seq += 1
            stored = self._state.append_log({
                'id': f'log-voice-{self._voice_event_seq:06d}',
                'timestamp': now_iso(),
                'level': 'warn' if event_name == 'decode_failed' else level,
                'module': 'voice.gateway',
                'taskId': task_id,
                'requestId': request_id,
                'correlationId': correlation_id,
                'taskRunId': task_run_id,
                'episodeId': episode_id or task_run_id,
                'stage': str(payload.get('stage', 'voice_telemetry')) or 'voice_telemetry',
                'errorCode': str(payload.get('errorCode', '')) or None,
                'operatorActionable': bool(payload.get('operatorActionable', False)),
                'event': f'voice.event.{event_name}',
                'message': str(payload.get('message', payload.get('status', 'voice event received'))),
                'payload': dict(payload),
            })
            self._state.update_task_from_log(stored)
            audit = self._state.append_audit({
                'id': new_request_id('audit'),
                'timestamp': now_iso(),
                'action': 'voice.event',
                'status': 'observed',
                'role': 'system',
                'requestId': request_id or new_request_id('voice'),
                'correlationId': correlation_id,
                'taskId': task_id,
                'stage': str(payload.get('stage', 'voice_telemetry')) or 'voice_telemetry',
                'errorCode': str(payload.get('errorCode', '')) or None,
                'operatorActionable': bool(payload.get('operatorActionable', False)),
                'message': str(payload.get('message', payload.get('status', 'voice event received'))),
                'payload': dict(payload),
            })
            receipt = self._state.append_command_receipt({
                'id': new_request_id('receipt'),
                'timestamp': now_iso(),
                'action': 'voice.event',
                'status': 'observed',
                'role': 'system',
                'requestId': request_id or new_request_id('voice'),
                'correlationId': correlation_id,
                'commandPlane': 'voice_observability',
                'receiptClass': receipt_class_for_command_plane('voice_observability'),
                'executionBound': bool(payload.get('actionExecutionBound', execution_bound_for_command_plane('voice_observability'))),
                'errorCode': str(payload.get('errorCode', '')) or None,
                'operatorActionable': bool(payload.get('operatorActionable', False)),
                'message': str(payload.get('message', payload.get('status', 'voice event received'))),
                'payload': dict(payload),
            })
            self._publisher.publish_topics_threadsafe('diagnostics', extra_events=[('log.event.created', stored), ('voice.event.created', stored), ('audit.event.created', audit), ('command.receipt.created', receipt)])

        def _on_log_event(self, msg: TaskEvent) -> None:
            payload = map_log_event_message(msg)
            context_payload = self._state.request_context_payload(str(payload.get('taskId') or '')) or {}
            payload['requestId'] = payload.get('requestId') or context_payload.get('requestId')
            payload['correlationId'] = payload.get('correlationId') or context_payload.get('correlationId')
            payload['taskRunId'] = payload.get('taskRunId') or context_payload.get('taskRunId')
            payload['episodeId'] = payload.get('episodeId') or context_payload.get('episodeId') or payload.get('taskRunId') or context_payload.get('taskRunId')
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
