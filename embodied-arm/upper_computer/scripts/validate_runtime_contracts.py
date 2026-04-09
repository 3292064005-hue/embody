#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'backend' / 'embodied_arm_ws' / 'src'
CONFIG = SRC / 'arm_bringup' / 'config'
DESCRIPTION_CONFIG = SRC / 'arm_description' / 'config'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return payload if isinstance(payload, dict) else {}


def _normalize_place_profiles(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    profiles = payload.get('place_profiles', payload.get('profiles', payload))
    if not isinstance(profiles, dict):
        return {}
    result: dict[str, dict[str, float]] = {}
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        result[str(name)] = {
            'x': float(profile.get('x', 0.0)),
            'y': float(profile.get('y', 0.0)),
            'yaw': float(profile.get('yaw', 0.0)),
        }
    return result


def _normalize_joint_limits(payload: dict[str, Any]) -> dict[str, dict[str, float | bool]]:
    joints = payload.get('joint_limits', {}) if isinstance(payload, dict) else {}
    if not isinstance(joints, dict):
        return {}
    result: dict[str, dict[str, float | bool]] = {}
    for name, profile in joints.items():
        if not isinstance(profile, dict):
            continue
        result[str(name)] = {
            'has_position_limits': bool(profile.get('has_position_limits', False)),
            'min_position': float(profile.get('min_position', 0.0)),
            'max_position': float(profile.get('max_position', 0.0)),
        }
    return result


def _issues() -> list[str]:
    issues: list[str] = []
    launch_factory = SRC / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
    motion_executor = SRC / 'arm_motion_executor' / 'arm_motion_executor' / 'motion_executor_node.py'
    dispatcher = SRC / 'arm_hardware_bridge' / 'arm_hardware_bridge' / 'hardware_command_dispatcher_node.py'
    topic_names = SRC / 'arm_common' / 'arm_common' / 'topic_names.py'
    runtime_profiles = CONFIG / 'runtime_profiles.yaml'
    runtime_manifest = ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json'
    promotion_receipts = CONFIG / 'runtime_promotion_receipts.yaml'
    placement_profiles = CONFIG / 'placement_profiles.yaml'
    default_calibration = CONFIG / 'default_calibration.yaml'
    safety_limits = CONFIG / 'safety_limits.yaml'
    joint_limits = DESCRIPTION_CONFIG / 'joint_limits.yaml'

    motion_text = _read(motion_executor)
    dispatch_text = _read(dispatcher)
    topics_text = _read(topic_names)
    profiles_text = _read(runtime_profiles)
    launch_text = _read(launch_factory)
    gateway_state = ROOT / 'gateway' / 'state.py'
    manifest_text = _read(runtime_manifest)
    state_text = _read(gateway_state)

    if 'FAULT_REPORT' not in topics_text:
        issues.append('TopicNames missing FAULT_REPORT')
    if 'CAMERA_IMAGE_COMPAT' not in topics_text or 'CAMERA_IMAGE_RAW' not in topics_text:
        issues.append('TopicNames must expose both CAMERA_IMAGE_RAW and CAMERA_IMAGE_COMPAT')
    camera_runtime_text = _read(SRC / 'arm_camera_driver' / 'arm_camera_driver' / 'camera_runtime_node.py')
    if 'self._image_pub = self.create_managed_publisher(Image, TopicNames.CAMERA_IMAGE_RAW, 10)' not in camera_runtime_text:
        issues.append('camera runtime must publish standard sensor_msgs/Image on TopicNames.CAMERA_IMAGE_RAW')
    if 'create_subscription(String, str(self.get_parameter(\'legacy_topic_name\').value), self._on_external_frame, 20)' not in camera_runtime_text:
        issues.append('camera runtime must retain legacy JSON ingress on the compatibility topic')
    if "self._publish_frame_summary(summary, publish_standard_image=self._should_publish_standard_image(source='compat'))" not in camera_runtime_text:
        issues.append('camera runtime must gate compatibility re-publish through _should_publish_standard_image to avoid loopback duplication')
    if 'safety_limits_path' not in motion_text:
        issues.append('motion executor must declare safety_limits_path and consume runtime safety authority')
    if 'TopicNames.FAULT_REPORT' not in motion_text:
        issues.append('motion executor must subscribe to TopicNames.FAULT_REPORT')
    if 'TopicNames.SYSTEM_FAULT' in motion_text:
        issues.append('motion executor still references removed TopicNames.SYSTEM_FAULT path')
    if 'create_subscription(HardwareState, TopicNames.HARDWARE_STATE' not in motion_text:
        issues.append('motion executor must consume typed HardwareState messages')
    if "'command_id'" not in dispatch_text:
        issues.append('dispatcher feedback must carry command_id correlation')
    if "'forward_hardware_commands': forward_hardware_commands" not in launch_text:
        issues.append('launch factory must pass forward_hardware_commands into motion executor')
    if 'forward_hardware_commands:' not in profiles_text:
        issues.append('runtime profiles missing forward_hardware_commands lane flag')
    if 'frame_ingress_mode:' not in profiles_text:
        issues.append('runtime profiles missing frame_ingress_mode lane flag')
    if 'hardware_execution_mode:' not in profiles_text:
        issues.append('runtime profiles missing hardware_execution_mode lane flag')
    if 'runtime_promotion_receipts' not in launch_text and 'RUNTIME_PROMOTION_RECEIPT_PATH' not in launch_text:
        issues.append('launch factory must consume runtime promotion receipts for validated_live promotion')
    if 'load_runtime_promotion_receipts' not in state_text:
        issues.append('gateway state must consume runtime promotion receipts when inferring runtimeTier')
    if "result.status in {'failed', 'timeout', 'canceled', 'fault'}" not in motion_text:
        issues.append('motion executor must treat raw fault feedback as a terminal execution failure')
    if 'self._executor.mark_all_failed' not in motion_text:
        issues.append('motion executor fault-report path must fail active handles before timeout fallback')
    if '_dispatch_failure_feedback' not in dispatch_text:
        issues.append('hardware dispatcher must publish immediate failed feedback on dispatch exceptions')
    if 'safety_limits_path' not in dispatch_text or '_validate_command_against_safety' not in dispatch_text:
        issues.append('hardware dispatcher must validate commands against runtime safety limits before serial dispatch')
    if '"laneCapabilities"' not in manifest_text:
        issues.append('generated runtime contract manifest missing laneCapabilities summary')

    receipt_payload = _yaml(promotion_receipts)
    if not isinstance(receipt_payload.get('validated_live'), dict) or bool(receipt_payload.get('validated_live', {}).get('promoted', False)):
        issues.append('validated_live promotion receipt must exist and remain fail-closed by default')

    placement = _normalize_place_profiles(_yaml(placement_profiles))
    calibration_payload = _yaml(default_calibration)
    calibration_place_profiles = _normalize_place_profiles(calibration_payload.get('placement', {})) if isinstance(calibration_payload.get('placement'), dict) else {}
    if placement != calibration_place_profiles:
        issues.append('default_calibration placement profiles must mirror placement_profiles.yaml exactly')
    if str(calibration_payload.get('placement', {}).get('source', '') or '') != 'arm_bringup/config/placement_profiles.yaml':
        issues.append('default_calibration placement source marker must point to placement_profiles.yaml')

    safety_payload = _yaml(safety_limits)
    safety_joint_limits = _normalize_joint_limits(safety_payload)
    description_joint_limits = _normalize_joint_limits(_yaml(joint_limits))
    if safety_joint_limits != description_joint_limits:
        issues.append('safety_limits joint_limits must mirror arm_description/config/joint_limits.yaml exactly')
    authority = safety_payload.get('authority', {}) if isinstance(safety_payload.get('authority'), dict) else {}
    if str(authority.get('source', '') or '') != 'arm_bringup/config/safety_limits.yaml':
        issues.append('safety_limits authority.source must point to arm_bringup/config/safety_limits.yaml')
    if str(authority.get('mirrored_joint_source', '') or '') != 'arm_description/config/joint_limits.yaml':
        issues.append('safety_limits authority.mirrored_joint_source must point to arm_description/config/joint_limits.yaml')
    if not bool(authority.get('runtime_enforced', False)):
        issues.append('safety_limits authority.runtime_enforced must remain true after runtime authority closure')
    enforcement_nodes = authority.get('enforcement_nodes', []) if isinstance(authority.get('enforcement_nodes'), list) else []
    if 'arm_motion_executor' not in enforcement_nodes or 'arm_hardware_bridge/hardware_command_dispatcher' not in enforcement_nodes:
        issues.append('safety_limits enforcement_nodes must include motion executor and hardware dispatcher')
    manual_limits = safety_payload.get('manual_command_limits', {}) if isinstance(safety_payload.get('manual_command_limits'), dict) else {}
    if float(manual_limits.get('max_servo_cartesian_delta', 0.0) or 0.0) <= 0.0:
        issues.append('safety_limits manual_command_limits.max_servo_cartesian_delta must be positive')
    if float(manual_limits.get('max_jog_joint_step_deg', 0.0) or 0.0) <= 0.0:
        issues.append('safety_limits manual_command_limits.max_jog_joint_step_deg must be positive')
    return issues


def main() -> int:
    issues = _issues()
    if issues:
        for item in issues:
            print(f'[runtime-contracts] {item}')
        return 1
    print('[runtime-contracts] PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
