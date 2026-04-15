from __future__ import annotations

from pathlib import Path
import json

from runtime_authority import evaluate_promotion_receipt


def test_validated_live_receipt_auto_promotes_when_required_evidence_is_satisfied() -> None:
    receipt = {
        'tier_name': 'validated_live',
        'promotion_mode': 'automatic_when_ready',
        'promoted': False,
        'required_evidence': [
            'validated_live_backbone_declared',
            'target_runtime_gate_passed',
            'hil_gate_passed',
            'release_checklist_signed',
        ],
        'evidence': [
            'validated_live_backbone_declared',
            'target_runtime_gate_passed',
            'hil_gate_passed',
            'release_checklist_signed',
        ],
    }
    authority = {
        'runtime_lanes': {
            'real_validated_live': {
                'planning_backend_profile': 'validated_live_bridge',
                'execution_backbone': 'ros2_control',
                'execution_backbone_declared': True,
                'enable_ros2_control': True,
                'hardware_execution_mode': 'ros2_control_live',
                'camera_source': 'topic',
                'esp32_frame_ingress_live': True,
                'frame_ingress_mode': 'live_camera_stream',
                'scene_provider_mode': 'runtime_service',
                'grasp_provider_mode': 'runtime_service',
                'forward_hardware_commands': True,
                'hardware_command_path': 'ros2_control',
            }
        },
        'planning_backends': {
            'validated_live_bridge': {
                'mode': 'validated_live_bridge',
                'declared': True,
            }
        },
        'validated_live_backbones': {
            'validated_live': {
                'owner': 'ros2_control',
                'planning_backend_profile': 'validated_live_bridge',
                'controller_manager_package': 'controller_manager',
                'hardware_interface_package': 'arm_hardware_interface',
                'vision_backbone': 'runtime_scene_service',
                'hardware_command_path': 'ros2_control',
            }
        }
    }
    repo_root = Path(__file__).resolve().parents[2]
    gate_report = repo_root / 'artifacts' / 'release_gates' / 'target_runtime_gate.json'
    gate_report.parent.mkdir(parents=True, exist_ok=True)
    gate_report.write_text(json.dumps({'targetGate': 'passed', 'hilGate': 'passed', 'releaseChecklistGate': 'passed'}), encoding='utf-8')
    evidence = {
        'evidence': {
            'target_runtime_gate_passed': {'status': 'passed', 'artifact': 'docs/evidence/validated_live/target_runtime_gate.md', 'gate_field': 'targetGate', 'gate_report': str(gate_report)},
            'hil_gate_passed': {'status': 'passed', 'artifact': 'docs/evidence/validated_live/hil_smoke_report.md', 'gate_field': 'hilGate', 'gate_report': str(gate_report)},
            'release_checklist_signed': {'status': 'passed', 'artifact': 'docs/evidence/validated_live/release_checklist.md'},
        }
    }
    status = evaluate_promotion_receipt(receipt, authority=authority, evidence_manifest=evidence)
    assert status.mode == 'automatic_when_ready'
    assert status.promoted is True
    assert status.effective is True
    assert status.missing == ()


def test_validated_live_receipt_stays_fail_closed_when_automatic_evidence_is_missing() -> None:
    receipt = {
        'tier_name': 'validated_live',
        'promotion_mode': 'automatic_when_ready',
        'required_evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed'],
        'evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed'],
    }
    authority = {'validated_live_backbones': {}}
    evidence = {'evidence': {'target_runtime_gate_passed': {'status': 'not_executed'}}}
    status = evaluate_promotion_receipt(receipt, authority=authority, evidence_manifest=evidence)
    assert status.promoted is False
    assert status.effective is False
    assert 'validated_live_backbone_declared' in status.missing
