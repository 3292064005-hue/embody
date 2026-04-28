from __future__ import annotations

from arm_common.topic_names import TopicNames
from arm_readiness_manager.readiness import ReadinessCheck, ReadinessSnapshot


def test_topic_contract_exposes_authoritative_and_compat_vision_topics():
    assert TopicNames.VISION_TARGET == '/arm/vision/target'
    assert TopicNames.VISION_TARGETS == '/arm/vision/targets'
    assert TopicNames.CAMERA_FRAME_SUMMARY == '/arm/camera/frame_summary'
    assert TopicNames.CAMERA_HEALTH_SUMMARY == '/arm/camera/health'


def test_readiness_snapshot_exports_layered_semantics():
    checks = {
        'ros2': ReadinessCheck(name='ros2', ok=True),
        'task_orchestrator': ReadinessCheck(name='task_orchestrator', ok=True),
        'motion_planner': ReadinessCheck(name='motion_planner', ok=True),
        'motion_executor': ReadinessCheck(name='motion_executor', ok=True),
        'scene_runtime_service': ReadinessCheck(name='scene_runtime_service', ok=True),
        'grasp_runtime_service': ReadinessCheck(name='grasp_runtime_service', ok=True),
        'hardware_bridge': ReadinessCheck(name='hardware_bridge', ok=True),
        'calibration': ReadinessCheck(name='calibration', ok=True),
        'profiles': ReadinessCheck(name='profiles', ok=True),
    }
    snapshot = ReadinessSnapshot(
        checks=checks,
        mode='idle',
        required=('ros2', 'task_orchestrator', 'scene_runtime_service', 'grasp_runtime_service', 'hardware_bridge', 'calibration', 'profiles'),
        controller_mode='idle',
        runtime_phase='idle',
        task_stage='done',
    )
    payload = snapshot.as_dict()
    assert payload['runtimeHealthy'] is True
    assert payload['modeReady'] is True
    assert payload['allReady'] is True
    assert payload['commandSummary']['readyCount'] >= 1
    assert payload['runtimeRequiredChecks']


def test_home_command_requires_authoritative_hardware_bridge():
    checks = {
        'ros2': ReadinessCheck(name='ros2', ok=True),
        'task_orchestrator': ReadinessCheck(name='task_orchestrator', ok=True),
        'motion_planner': ReadinessCheck(name='motion_planner', ok=True),
        'motion_executor': ReadinessCheck(name='motion_executor', ok=True),
        'scene_runtime_service': ReadinessCheck(name='scene_runtime_service', ok=True),
        'grasp_runtime_service': ReadinessCheck(name='grasp_runtime_service', ok=True),
        'hardware_bridge': ReadinessCheck(name='hardware_bridge', ok=False, detail='hardware_offline'),
        'calibration': ReadinessCheck(name='calibration', ok=True),
        'profiles': ReadinessCheck(name='profiles', ok=True),
    }
    snapshot = ReadinessSnapshot(checks=checks, mode='idle', required=('ros2', 'task_orchestrator', 'scene_runtime_service', 'grasp_runtime_service', 'hardware_bridge', 'calibration', 'profiles'))
    policies = snapshot.command_policies()
    assert policies['home']['allowed'] is False
    assert 'hardware_bridge' in policies['home']['reason']


def test_manual_commands_no_longer_require_authoritative_planner_in_maintenance_mode():
    checks = {
        'ros2': ReadinessCheck(name='ros2', ok=True),
        'task_orchestrator': ReadinessCheck(name='task_orchestrator', ok=True),
        'motion_planner': ReadinessCheck(name='motion_planner', ok=False, detail='planner_contract_only'),
        'motion_executor': ReadinessCheck(name='motion_executor', ok=False, detail='executor_contract_only'),
        'scene_runtime_service': ReadinessCheck(name='scene_runtime_service', ok=True),
        'grasp_runtime_service': ReadinessCheck(name='grasp_runtime_service', ok=True),
        'hardware_bridge': ReadinessCheck(name='hardware_bridge', ok=True),
        'calibration': ReadinessCheck(name='calibration', ok=True),
        'profiles': ReadinessCheck(name='profiles', ok=True),
    }
    snapshot = ReadinessSnapshot(checks=checks, mode='maintenance', required=('ros2', 'task_orchestrator', 'hardware_bridge'))
    policies = snapshot.command_policies()
    assert policies['jog']['allowed'] is True
    assert policies['servoCartesian']['allowed'] is True
    assert policies['gripper']['allowed'] is True


def test_recover_command_is_exported_as_public_policy():
    checks = {
        'ros2': ReadinessCheck(name='ros2', ok=True),
        'task_orchestrator': ReadinessCheck(name='task_orchestrator', ok=True),
        'motion_planner': ReadinessCheck(name='motion_planner', ok=False, detail='planner_contract_only'),
        'motion_executor': ReadinessCheck(name='motion_executor', ok=False, detail='executor_contract_only'),
        'scene_runtime_service': ReadinessCheck(name='scene_runtime_service', ok=True),
        'grasp_runtime_service': ReadinessCheck(name='grasp_runtime_service', ok=True),
        'hardware_bridge': ReadinessCheck(name='hardware_bridge', ok=True),
        'calibration': ReadinessCheck(name='calibration', ok=True),
        'profiles': ReadinessCheck(name='profiles', ok=True),
    }
    snapshot = ReadinessSnapshot(checks=checks, mode='maintenance', required=('ros2', 'task_orchestrator', 'hardware_bridge'))
    policies = snapshot.command_policies()
    assert policies['recover']['allowed'] is True
    assert 'recover' in policies
