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


def _resolve_repo_peer_path(*parts: str) -> Path:
    primary = ROOT.parent.joinpath(*parts)
    if primary.exists():
        return primary
    return ROOT.joinpath(*parts)


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
    runtime_schema = ROOT / 'docs' / 'generated' / 'runtime_contract_schema.json'
    openapi_yaml = ROOT / 'gateway' / 'openapi' / 'runtime_api.yaml'
    frontend_api_generated = ROOT / 'frontend' / 'src' / 'api' / 'generated' / 'index.ts'
    promotion_receipts = CONFIG / 'runtime_promotion_receipts.yaml'
    runtime_lane_aliases = CONFIG / 'runtime_lane_aliases.yaml'
    firmware_semantic_profiles = CONFIG / 'firmware_semantic_profiles.yaml'
    esp32_generated_header = _resolve_repo_peer_path('esp32s3_platformio', 'include', 'generated', 'runtime_semantic_profile.hpp')
    esp32_project_config = _resolve_repo_peer_path('esp32s3_platformio', 'include', 'project_config.hpp')
    esp32_platformio = _resolve_repo_peer_path('esp32s3_platformio', 'platformio.ini')
    placement_profiles = CONFIG / 'placement_profiles.yaml'
    default_calibration = CONFIG / 'default_calibration.yaml'
    safety_limits = CONFIG / 'safety_limits.yaml'
    joint_limits = DESCRIPTION_CONFIG / 'joint_limits.yaml'

    motion_text = _read(motion_executor)
    dispatch_text = _read(dispatcher)
    topics_text = _read(topic_names)
    profiles_text = _read(runtime_profiles)
    alias_text = _read(runtime_lane_aliases)
    firmware_profiles_text = _read(firmware_semantic_profiles)
    launch_text = _read(launch_factory)
    gateway_state = ROOT / 'gateway' / 'state.py'
    manifest_text = _read(runtime_manifest)
    schema_text = _read(runtime_schema) if runtime_schema.exists() else ''
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
    if 'RUNTIME_LANE_ALIAS_PATH' not in launch_text or '_load_runtime_lane_alias_maps' not in launch_text:
        issues.append('launch factory must consume generated runtime_lane_aliases.yaml instead of hard-coded alias tables')
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
    if '"governance"' not in manifest_text:
        issues.append('generated runtime contract manifest missing runtime governance summary')
    if '"experimentalRuntimeLanes"' not in manifest_text:
        issues.append('generated runtime contract manifest missing experimental runtime lane classification')
    if '"acceptanceMatrix"' not in manifest_text:
        issues.append('generated runtime contract manifest missing runtime acceptance matrix')
    if not schema_text.strip():
        issues.append('generated runtime contract schema missing')
    elif '"validatedLiveReleaseSlice"' not in schema_text:
        issues.append('generated runtime contract schema missing validatedLiveReleaseSlice projection')
    if '"validatedLiveReleaseSlice"' not in manifest_text:
        issues.append('generated runtime contract manifest missing validatedLiveReleaseSlice projection')
    if 'OFFICIAL_RUNTIME_LANES =' in launch_text or 'EXPERIMENTAL_RUNTIME_LANES =' in launch_text:
        issues.append('launch_factory.py must not hand-maintain official/experimental runtime lane lists')
    if 'LEGACY_EXPERIMENTAL_RUNTIME_LANE_ALIASES' not in launch_text:
        issues.append('launch_factory.py must explicitly quarantine retired live aliases')
    if 'resolved:' not in alias_text:
        issues.append('runtime_lane_aliases.yaml must expose resolved alias projections')
    if 'default_profile:' not in firmware_profiles_text:
        issues.append('firmware_semantic_profiles.yaml must record the default firmware semantic profile')

    profiles_payload = _yaml(runtime_profiles)
    governance_payload = _yaml(CONFIG / 'runtime_authority.yaml').get('runtime_governance', {}) if isinstance(_yaml(CONFIG / 'runtime_authority.yaml'), dict) else {}
    official_lanes = governance_payload.get('official_runtime_lanes', []) if isinstance(governance_payload, dict) else []
    experimental_lanes = governance_payload.get('experimental_runtime_lanes', []) if isinstance(governance_payload, dict) else []
    if sorted(official_lanes) == sorted(experimental_lanes) or set(official_lanes) & set(experimental_lanes):
        issues.append('runtime authority governance must keep official and experimental runtime lanes disjoint')
    manifest_payload = json.loads(manifest_text) if manifest_text.strip() else {}
    manifest_runtime = manifest_payload.get('runtime', {}) if isinstance(manifest_payload, dict) else {}
    manifest_governance = manifest_runtime.get('governance', {}) if isinstance(manifest_runtime.get('governance'), dict) else {}
    task_templates = manifest_payload.get('tasks', {}).get('templates', []) if isinstance(manifest_payload.get('tasks'), dict) else []
    if not task_templates or not all(isinstance(item, dict) and item.get('graphKey') and isinstance(item.get('taskGraph'), dict) for item in task_templates):
        issues.append('generated runtime contract manifest must expose task graph descriptors for all task templates')

    runtime_contract = manifest_payload.get('runtime', {}) if isinstance(manifest_payload.get('runtime'), dict) else {}
    release_slice = runtime_contract.get('validatedLiveReleaseSlice', {}) if isinstance(runtime_contract, dict) else {}
    smoke_tests = release_slice.get('smoke_tests', []) if isinstance(release_slice, dict) else []
    if not smoke_tests or not all((ROOT / str(item)).exists() for item in smoke_tests):
        issues.append('validated-live release slice smoke_tests must reference existing repository tests')

    openapi_text = _read(openapi_yaml)
    frontend_api_text = _read(frontend_api_generated)
    if 'StartTaskDecisionResponse' not in openapi_text:
        issues.append('OpenAPI runtime_api.yaml missing task-start response schema: StartTaskDecisionResponse')
    for token in ('episodeId', 'pluginKey', 'graphKey'):
        if token not in openapi_text:
            issues.append(f'OpenAPI runtime_api.yaml missing task-start contract token: {token}')
        if token not in frontend_api_text:
            issues.append(f'frontend generated runtime API missing task-start contract token: {token}')
    if list(manifest_governance.get('officialRuntimeLanes', [])) != list(official_lanes):
        issues.append('generated runtime contract manifest officialRuntimeLanes drift from runtime_authority.yaml')
    if list(manifest_governance.get('experimentalRuntimeLanes', [])) != list(experimental_lanes):
        issues.append('generated runtime contract manifest experimentalRuntimeLanes drift from runtime_authority.yaml')
    acceptance_matrix = manifest_runtime.get('acceptanceMatrix', {}) if isinstance(manifest_runtime.get('acceptanceMatrix'), dict) else {}
    for lane_name in official_lanes:
        payload = profiles_payload.get(lane_name, {}) if isinstance(profiles_payload, dict) else {}
        if str(payload.get('public_runtime_tier', '') or '') == 'validated_live':
            issues.append(f'official runtime lane {lane_name} must not project validated_live as a public tier')
        acceptance = acceptance_matrix.get(lane_name, {}) if isinstance(acceptance_matrix.get(lane_name), dict) else {}
        if str(acceptance.get('deliveryTrack', '') or '') != 'official_active':
            issues.append(f'acceptance matrix must classify official runtime lane {lane_name} as official_active')
    for lane_name in experimental_lanes:
        payload = profiles_payload.get(lane_name, {}) if isinstance(profiles_payload, dict) else {}
        if str(payload.get('runtime_delivery_track', '') or '') != 'experimental':
            issues.append(f'experimental runtime lane {lane_name} must project runtime_delivery_track=experimental')
        acceptance = acceptance_matrix.get(lane_name, {}) if isinstance(acceptance_matrix.get(lane_name), dict) else {}
        if str(acceptance.get('deliveryTrack', '') or '') != 'experimental':
            issues.append(f'acceptance matrix must classify experimental runtime lane {lane_name} as experimental')
        if 'requiredEvidence' not in acceptance or not list(acceptance.get('requiredEvidence', [])):
            issues.append(f'acceptance matrix must record required evidence for experimental lane {lane_name}')
    if 'simulated_local_only' in _read(SRC / 'arm_readiness_manager' / 'arm_readiness_manager' / 'contract_defs.py'):
        issues.append('readiness contract must not retain the deprecated simulated_local_only mode token')

    alias_payload = _yaml(runtime_lane_aliases)
    alias_resolved = alias_payload.get('resolved', {}) if isinstance(alias_payload.get('resolved'), dict) else {}
    manifest_aliases = manifest_runtime.get('laneAliases', {}) if isinstance(manifest_runtime.get('laneAliases'), dict) else {}
    if manifest_aliases != dict(alias_resolved.get('active', {})):
        issues.append('generated runtime contract manifest laneAliases drift from runtime_lane_aliases.yaml')
    if manifest_runtime.get('compatibilityLaneAliases', {}) != dict(alias_resolved.get('compatibility', {})):
        issues.append('generated runtime contract manifest compatibilityLaneAliases drift from runtime_lane_aliases.yaml')
    if manifest_runtime.get('experimentalLaneAliases', {}) != dict(alias_resolved.get('experimental', {})):
        issues.append('generated runtime contract manifest experimentalLaneAliases drift from runtime_lane_aliases.yaml')
    if manifest_runtime.get('legacyExperimentalLaneAliases', {}) != dict(alias_resolved.get('retired', {})):
        issues.append('generated runtime contract manifest legacyExperimentalLaneAliases drift from runtime_lane_aliases.yaml')

    firmware_payload = _yaml(firmware_semantic_profiles)
    firmware_manifest = manifest_runtime.get('firmwareSemanticProfiles', {}) if isinstance(manifest_runtime.get('firmwareSemanticProfiles'), dict) else {}
    if firmware_manifest != dict(firmware_payload.get('esp32', {})):
        issues.append('generated runtime contract manifest firmwareSemanticProfiles drift from firmware_semantic_profiles.yaml')
    header_text = _read(esp32_generated_header)
    project_config_text = _read(esp32_project_config)
    platformio_text = _read(esp32_platformio)
    if 'EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_PREVIEW_RESERVED' not in header_text:
        issues.append('generated ESP32 semantic header must expose preview_reserved profile macro')
    if 'include "generated/runtime_semantic_profile.hpp"' not in project_config_text:
        issues.append('ESP32 project_config.hpp must include the generated runtime semantic profile header')
    if 'EMBODIED_ARM_DEFAULT_STREAM_SEMANTIC' not in project_config_text:
        issues.append('ESP32 project_config.hpp must source default stream semantics from the generated authority header')
    if 'EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE=EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_PREVIEW_RESERVED' not in platformio_text:
        issues.append('ESP32 platformio.ini must pin the default semantic profile to preview_reserved')

    receipt_payload = _yaml(promotion_receipts)
    live_receipt = receipt_payload.get('validated_live') if isinstance(receipt_payload.get('validated_live'), dict) else None
    if not isinstance(live_receipt, dict):
        issues.append('validated_live promotion receipt must exist')
    else:
        mode = str(live_receipt.get('promotion_mode', 'manual') or 'manual').strip().lower()
        if mode not in {'manual', 'automatic_when_ready'}:
            issues.append('validated_live promotion receipt uses unsupported promotion_mode')
        if mode == 'manual' and bool(live_receipt.get('promoted', False)):
            issues.append('validated_live manual promotion receipt must remain fail-closed by default')
        if mode == 'automatic_when_ready' and bool(live_receipt.get('promoted', False)) and not bool(live_receipt.get('effective', False)):
            issues.append('validated_live automatic promotion receipt cannot report promoted without effective evidence closure')

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
