from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

import gateway.runtime_config as runtime_config
from gateway.runtime_config import (
    clear_runtime_config_caches,
    current_runtime_config_version,
    load_default_calibration_payload,
    load_manual_command_limits,
    load_place_profiles,
    load_runtime_promotion_receipt_details,
    load_runtime_promotion_receipts,
    load_release_gate_details,
    load_firmware_semantic_profiles,
    resolve_active_runtime_profile,
)


def _write_runtime_authority(path: Path, *, backend_declared: bool, backbone_declared: bool) -> None:
    authority = yaml.safe_load((runtime_config.RUNTIME_AUTHORITY_PATH).read_text(encoding='utf-8'))
    authority['planning_backends']['validated_live_bridge']['declared'] = backend_declared
    for lane_name in ('live_control', 'real_validated_live'):
        if lane_name not in authority.get('runtime_lanes', {}):
            continue
        authority['runtime_lanes'][lane_name]['execution_backbone_declared'] = backbone_declared
        authority['runtime_lanes'][lane_name]['enable_ros2_control'] = True
        authority['runtime_lanes'][lane_name]['execution_backbone'] = 'ros2_control'
    path.write_text(yaml.safe_dump(authority, sort_keys=False), encoding='utf-8')


def _write_target_runtime_gate_report(
    path: Path,
    *,
    target_status: str = 'not_executed',
    hil_status: str = 'not_executed',
    checklist_status: str = 'not_executed',
) -> None:
    has_blocking = any(status != 'passed' for status in (target_status, hil_status, checklist_status))
    release_gate = 'passed' if not has_blocking else ('failed' if 'failed' in {target_status, hil_status, checklist_status} else 'blocked')
    path.write_text(
        json.dumps(
            {
                'repoGate': 'passed',
                'targetGate': target_status,
                'hilGate': hil_status,
                'releaseChecklistGate': checklist_status,
                'releaseGate': release_gate,
                'hasBlockingStep': has_blocking,
            },
            indent=2,
        ),
        encoding='utf-8',
    )


def _write_validated_live_evidence(
    path: Path,
    *,
    target_status: str = 'not_executed',
    hil_status: str = 'not_executed',
    checklist_status: str = 'not_signed',
    gate_report: Path | None = None,
) -> None:
    gate_report_value = str(gate_report) if gate_report is not None else ''
    path.write_text(
        yaml.safe_dump(
            {
                'schema_version': 2,
                'evidence': {
                    'target_runtime_gate_passed': {
                        'status': target_status,
                        'artifact': 'docs/evidence/validated_live/target_runtime_gate.md',
                        'gate_field': 'targetGate',
                        'gate_report': gate_report_value,
                    },
                    'hil_gate_passed': {
                        'status': hil_status,
                        'artifact': 'docs/evidence/validated_live/hil_smoke_report.md',
                        'gate_field': 'hilGate',
                        'gate_report': gate_report_value,
                    },
                    'release_checklist_signed': {
                        'status': checklist_status,
                        'artifact': 'docs/evidence/validated_live/release_checklist.md',
                    },
                },
            },
            sort_keys=False,
        ),
        encoding='utf-8',
    )


def test_gateway_runtime_config_loads_authoritative_place_profiles() -> None:
    profiles = load_place_profiles()
    assert profiles['default'] == {'x': 0.2, 'y': 0.0, 'yaw': 0.0}
    assert profiles['bin_red'] == {'x': 0.25, 'y': 0.12, 'yaw': 0.0}
    assert profiles['bin_blue'] == {'x': 0.25, 'y': -0.12, 'yaw': 0.0}
    assert profiles['bin_green'] == {'x': 0.22, 'y': 0.02, 'yaw': 0.0}


def test_default_calibration_marks_external_placement_source() -> None:
    payload = load_default_calibration_payload()
    assert payload['placement']['source'] == 'arm_bringup/config/placement_profiles.yaml'


def test_gateway_runtime_config_loads_manual_command_limits_from_safety_authority() -> None:
    limits = load_manual_command_limits()
    assert limits['max_servo_cartesian_delta'] == 0.1
    assert limits['max_jog_joint_step_deg'] == 10.0


def test_runtime_config_auto_refreshes_manual_limits_when_file_changes(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / 'safety_limits.yaml'
    config_path.write_text(
        yaml.safe_dump({'manual_command_limits': {'max_servo_cartesian_delta': 0.1, 'max_jog_joint_step_deg': 10.0}}, sort_keys=False),
        encoding='utf-8',
    )
    monkeypatch.setattr(runtime_config, 'SAFETY_LIMITS_PATH', config_path)
    clear_runtime_config_caches()

    first_limits = load_manual_command_limits()
    first_version = current_runtime_config_version()
    assert first_limits['max_servo_cartesian_delta'] == 0.1
    assert first_limits['max_jog_joint_step_deg'] == 10.0

    time.sleep(0.01)
    config_path.write_text(
        yaml.safe_dump({'manual_command_limits': {'max_servo_cartesian_delta': 0.025, 'max_jog_joint_step_deg': 4.0}}, sort_keys=False),
        encoding='utf-8',
    )

    refreshed_limits = load_manual_command_limits()
    refreshed_version = current_runtime_config_version()
    assert refreshed_limits['max_servo_cartesian_delta'] == 0.025
    assert refreshed_limits['max_jog_joint_step_deg'] == 4.0
    assert refreshed_version != first_version


def test_runtime_config_auto_refreshes_promotion_receipts_when_authority_or_evidence_changes(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / 'runtime_promotion_receipts.yaml'
    authority_path = tmp_path / 'runtime_authority.yaml'
    evidence_path = tmp_path / 'validated_live_evidence.yaml'
    gate_report = tmp_path / 'target_runtime_gate.json'
    _write_runtime_authority(authority_path, backend_declared=True, backbone_declared=True)
    _write_target_runtime_gate_report(gate_report, target_status='blocked', hil_status='not_executed', checklist_status='not_executed')
    _write_validated_live_evidence(evidence_path, target_status='not_executed', hil_status='not_executed', checklist_status='not_signed', gate_report=gate_report)
    config_path.write_text(
        yaml.safe_dump(
            {
                'validated_sim': {
                    'promoted': True,
                    'receipt_id': 'validated-sim-baseline',
                    'checked_by': 'repository-ci',
                    'checked_at': '2026-04-08T00:00:00Z',
                    'required_evidence': ['backend-active'],
                    'evidence': ['backend-active'],
                },
                'validated_live': {
                    'promoted': True,
                    'receipt_id': 'live-promoted-001',
                    'checked_by': 'release-bot',
                    'checked_at': '2026-04-09T00:00:00Z',
                    'required_evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'],
                    'evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'],
                },
            },
            sort_keys=False,
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(runtime_config, 'RUNTIME_PROMOTION_RECEIPT_PATH', config_path)
    monkeypatch.setattr(runtime_config, 'RUNTIME_AUTHORITY_PATH', authority_path)
    monkeypatch.setattr(runtime_config, 'VALIDATED_LIVE_EVIDENCE_PATH', evidence_path)
    monkeypatch.setenv('EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE', str(gate_report))
    clear_runtime_config_caches()

    first = load_runtime_promotion_receipts()
    first_version = current_runtime_config_version()
    assert first == {'validated_sim': True, 'validated_live': False}

    time.sleep(0.01)
    _write_target_runtime_gate_report(gate_report, target_status='passed', hil_status='passed', checklist_status='passed')
    _write_validated_live_evidence(evidence_path, target_status='passed', hil_status='passed', checklist_status='passed', gate_report=gate_report)

    refreshed = load_runtime_promotion_receipts()
    refreshed_version = current_runtime_config_version()
    assert refreshed == {'validated_sim': True, 'validated_live': True}
    assert refreshed_version != first_version


def test_runtime_config_marks_incomplete_live_receipt_as_ineffective(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / 'runtime_promotion_receipts.yaml'
    authority_path = tmp_path / 'runtime_authority.yaml'
    evidence_path = tmp_path / 'validated_live_evidence.yaml'
    gate_report = tmp_path / 'target_runtime_gate.json'
    _write_runtime_authority(authority_path, backend_declared=True, backbone_declared=True)
    _write_target_runtime_gate_report(gate_report, target_status='passed', hil_status='passed', checklist_status='blocked')
    _write_validated_live_evidence(evidence_path, target_status='passed', hil_status='passed', checklist_status='not_signed', gate_report=gate_report)
    config_path.write_text(
        yaml.safe_dump(
            {
                'validated_live': {
                    'promoted': True,
                    'receipt_id': 'live-promoted-001',
                    'checked_by': 'release-bot',
                    'checked_at': '2026-04-09T00:00:00Z',
                    'required_evidence': ['hil_gate_passed', 'release_checklist_signed'],
                    'evidence': ['hil_gate_passed'],
                },
            },
            sort_keys=False,
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(runtime_config, 'RUNTIME_PROMOTION_RECEIPT_PATH', config_path)
    monkeypatch.setattr(runtime_config, 'RUNTIME_AUTHORITY_PATH', authority_path)
    monkeypatch.setattr(runtime_config, 'VALIDATED_LIVE_EVIDENCE_PATH', evidence_path)
    monkeypatch.setenv('EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE', str(gate_report))
    clear_runtime_config_caches()

    details = load_runtime_promotion_receipt_details()
    assert details['validated_live']['effective'] is False
    assert details['validated_live']['missing_evidence'] == ['release_checklist_signed']
    assert load_runtime_promotion_receipts()['validated_live'] is False


def test_runtime_config_recomputes_effective_state_instead_of_trusting_yaml_flags(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / 'runtime_promotion_receipts.yaml'
    authority_path = tmp_path / 'runtime_authority.yaml'
    evidence_path = tmp_path / 'validated_live_evidence.yaml'
    gate_report = tmp_path / 'target_runtime_gate.json'
    _write_runtime_authority(authority_path, backend_declared=False, backbone_declared=False)
    _write_target_runtime_gate_report(gate_report, target_status='passed', hil_status='passed', checklist_status='passed')
    _write_validated_live_evidence(evidence_path, target_status='passed', hil_status='passed', checklist_status='passed', gate_report=gate_report)
    config_path.write_text(
        yaml.safe_dump(
            {
                'validated_live': {
                    'promoted': True,
                    'receipt_id': 'live-promoted-001',
                    'checked_by': 'release-bot',
                    'checked_at': '2026-04-09T00:00:00Z',
                    'required_evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'],
                    'evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'],
                    'effective': True,
                    'missing_evidence': [],
                },
            },
            sort_keys=False,
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(runtime_config, 'RUNTIME_PROMOTION_RECEIPT_PATH', config_path)
    monkeypatch.setattr(runtime_config, 'RUNTIME_AUTHORITY_PATH', authority_path)
    monkeypatch.setattr(runtime_config, 'VALIDATED_LIVE_EVIDENCE_PATH', evidence_path)
    monkeypatch.setenv('EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE', str(gate_report))
    clear_runtime_config_caches()

    details = load_runtime_promotion_receipt_details()
    assert details['validated_live']['effective'] is False
    assert details['validated_live']['missing_evidence'] == ['validated_live_backbone_declared']
    assert load_runtime_promotion_receipts()['validated_live'] is False


def test_runtime_config_reports_missing_validated_live_evidence_even_when_receipt_not_promoted(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / 'runtime_promotion_receipts.yaml'
    authority_path = tmp_path / 'runtime_authority.yaml'
    evidence_path = tmp_path / 'validated_live_evidence.yaml'
    gate_report = tmp_path / 'target_runtime_gate.json'
    _write_runtime_authority(authority_path, backend_declared=False, backbone_declared=False)
    _write_target_runtime_gate_report(gate_report, target_status='not_executed', hil_status='not_executed', checklist_status='not_executed')
    _write_validated_live_evidence(evidence_path, target_status='not_executed', hil_status='not_executed', checklist_status='not_executed', gate_report=gate_report)
    config_path.write_text(
        yaml.safe_dump(
            {
                'validated_live': {
                    'promoted': False,
                    'receipt_id': '',
                    'checked_by': '',
                    'checked_at': '',
                    'required_evidence': ['validated_live_backbone_declared', 'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'],
                    'evidence': [],
                    'reason': 'fail_closed_until_validated_live_backbone_and_release_gates_are_committed',
                },
            },
            sort_keys=False,
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(runtime_config, 'RUNTIME_PROMOTION_RECEIPT_PATH', config_path)
    monkeypatch.setattr(runtime_config, 'RUNTIME_AUTHORITY_PATH', authority_path)
    monkeypatch.setattr(runtime_config, 'VALIDATED_LIVE_EVIDENCE_PATH', evidence_path)
    monkeypatch.setenv('EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE', str(gate_report))
    clear_runtime_config_caches()

    details = load_runtime_promotion_receipt_details()
    assert details['validated_live']['effective'] is False
    assert details['validated_live']['missing_evidence'] == [
        'validated_live_backbone_declared',
        'target_runtime_gate_passed',
        'hil_gate_passed',
        'release_checklist_signed',
    ]


def test_runtime_config_defaults_report_new_validated_live_markers_when_receipt_file_missing(tmp_path: Path, monkeypatch) -> None:
    missing_receipt = tmp_path / 'missing_runtime_promotion_receipts.yaml'
    monkeypatch.setattr(runtime_config, 'RUNTIME_PROMOTION_RECEIPT_PATH', missing_receipt)
    clear_runtime_config_caches()

    details = load_runtime_promotion_receipt_details()
    assert details['validated_live']['missing_evidence'] == [
        'validated_live_backbone_declared',
        'target_runtime_gate_passed',
        'hil_gate_passed',
        'release_checklist_signed',
    ]


def test_runtime_config_loads_release_gate_projection(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / 'release_gate.json'
    report.write_text(json.dumps({'repoGate': 'passed', 'targetGate': 'blocked', 'hilGate': 'not_executed', 'releaseChecklistGate': 'not_executed', 'releaseGate': 'blocked', 'hasBlockingStep': True, 'blockingSteps': {'target_runtime_gate_passed': 'blocked'}}, indent=2), encoding='utf-8')
    monkeypatch.setenv('EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE', str(report))
    clear_runtime_config_caches()
    payload = load_release_gate_details()
    assert payload['targetGate'] == 'blocked'
    assert payload['hasBlockingStep'] is True
    assert payload['blockingSteps']['target_runtime_gate_passed'] == 'blocked'


def test_runtime_config_resolves_runtime_profile_alias_and_firmware_profiles() -> None:
    clear_runtime_config_caches()
    details = resolve_active_runtime_profile('official_runtime')
    assert details['activeRuntimeLane'] == 'sim_preview'
    assert details['resolvedFromAlias'] is True
    firmware = load_firmware_semantic_profiles()
    assert firmware['esp32']['default_profile'] == 'preview_reserved'
    assert 'preview_reserved' in firmware['esp32']['profiles']
