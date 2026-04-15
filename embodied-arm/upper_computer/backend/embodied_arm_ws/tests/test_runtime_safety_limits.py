from __future__ import annotations

from arm_backend_common.safety_limits import SafetyViolation, load_safety_limits
from arm_motion_executor.motion_executor_node import MotionExecutorNode
from arm_hardware_bridge.hardware_command_dispatcher_node import HardwareCommandDispatcherNode
from arm_camera_driver.camera_runtime_node import CameraRuntimeNode


def test_runtime_safety_limits_load_runtime_enforced_authority() -> None:
    limits = load_safety_limits()
    assert limits.source_path.endswith('arm_bringup/config/safety_limits.yaml')
    assert limits.manual_command_limits.max_servo_cartesian_delta == 0.1
    assert limits.manual_command_limits.max_jog_joint_step_deg == 10.0
    assert limits.joint_limits['gripper_joint'].max_position == 0.04


def test_motion_executor_rejects_execution_target_outside_joint_limits() -> None:
    node = MotionExecutorNode.__new__(MotionExecutorNode)
    node._safety_limits = load_safety_limits()
    try:
        MotionExecutorNode._validate_command_against_safety(node, {
            'kind': 'EXEC_STAGE',
            'execution_target': {
                'joint_names': ['joint_1'],
                'points': [{'positions': [9.0], 'time_from_start_sec': 0.5}],
            },
        })
    except SafetyViolation as exc:
        assert 'joint joint_1 target' in str(exc)
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError('motion executor must reject out-of-range execution targets')


def test_hardware_dispatcher_rejects_servo_delta_outside_runtime_limit() -> None:
    node = HardwareCommandDispatcherNode.__new__(HardwareCommandDispatcherNode)
    node._safety_limits = load_safety_limits()
    try:
        HardwareCommandDispatcherNode._validate_command_against_safety(node, {
            'kind': 'SERVO_CARTESIAN',
            'axis': 'x',
            'delta': 0.25,
        })
    except SafetyViolation as exc:
        assert 'servo delta' in str(exc)
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError('hardware dispatcher must reject oversized servo commands')


def test_hardware_dispatcher_rejects_joint_jog_outside_runtime_limit() -> None:
    node = HardwareCommandDispatcherNode.__new__(HardwareCommandDispatcherNode)
    node._safety_limits = load_safety_limits()
    try:
        HardwareCommandDispatcherNode._validate_command_against_safety(node, {
            'kind': 'JOG_JOINT',
            'jointIndex': 2,
            'direction': 1,
            'stepDeg': 15.0,
        })
    except SafetyViolation as exc:
        assert 'stepDeg' in str(exc)
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError('hardware dispatcher must reject oversized jog commands')


def test_camera_runtime_disables_compat_republish_by_default() -> None:
    node = CameraRuntimeNode.__new__(CameraRuntimeNode)
    node._publish_standard_image = True
    node._republish_compat_frames_as_standard_image = False
    assert CameraRuntimeNode._should_publish_standard_image(node, source='capture') is True
    assert CameraRuntimeNode._should_publish_standard_image(node, source='compat') is False


def test_hardware_dispatcher_accepts_set_joints_from_ros2_control_backbone_within_limits() -> None:
    node = HardwareCommandDispatcherNode.__new__(HardwareCommandDispatcherNode)
    node._safety_limits = load_safety_limits()
    payload = {
        'kind': 'SET_JOINTS',
        'producer': 'ros2_control_backbone',
        'command_plane': 'joint_stream',
        'joint_names': ['joint_1', 'joint_2'],
        'joint_positions': [0.2, -0.1],
        'gripper_position': 0.02,
    }
    HardwareCommandDispatcherNode._validate_command_origin(payload)
    HardwareCommandDispatcherNode._validate_command_against_safety(node, payload)


def test_hardware_dispatcher_rejects_set_joints_from_non_backbone_producer() -> None:
    payload = {
        'kind': 'SET_JOINTS',
        'producer': 'gateway_manual_control',
        'command_plane': 'joint_stream',
        'joint_names': ['joint_1'],
        'joint_positions': [0.0],
    }
    try:
        HardwareCommandDispatcherNode._validate_command_origin(payload)
    except SafetyViolation as exc:
        assert 'not authorized' in str(exc)
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError('hardware dispatcher must reject SET_JOINTS from non-backbone producers')


def test_hardware_dispatcher_rejects_set_joints_outside_runtime_limit() -> None:
    node = HardwareCommandDispatcherNode.__new__(HardwareCommandDispatcherNode)
    node._safety_limits = load_safety_limits()
    try:
        HardwareCommandDispatcherNode._validate_command_against_safety(node, {
            'kind': 'SET_JOINTS',
            'joint_names': ['joint_1'],
            'joint_positions': [9.0],
            'producer': 'ros2_control_backbone',
            'command_plane': 'joint_stream',
        })
    except SafetyViolation as exc:
        assert 'joint joint_1 target' in str(exc)
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError('hardware dispatcher must reject out-of-range SET_JOINTS commands')
