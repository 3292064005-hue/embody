from __future__ import annotations

from pathlib import Path
import importlib
import json
import sys
import types

import yaml

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'arm_bringup'))

launch = types.ModuleType('launch')
launch.LaunchDescription = type('LaunchDescription', (), {})
sys.modules.setdefault('launch', launch)

launch_actions = types.ModuleType('launch.actions')
launch_actions.DeclareLaunchArgument = type('DeclareLaunchArgument', (), {'__init__': lambda self, *args, **kwargs: None})
launch_actions.IncludeLaunchDescription = type('IncludeLaunchDescription', (), {'__init__': lambda self, *args, **kwargs: None})
launch_actions.OpaqueFunction = type('OpaqueFunction', (), {'__init__': lambda self, *args, **kwargs: None})
sys.modules.setdefault('launch.actions', launch_actions)

launch_conditions = types.ModuleType('launch.conditions')
launch_conditions.IfCondition = type('IfCondition', (), {'__init__': lambda self, *args, **kwargs: None})
sys.modules.setdefault('launch.conditions', launch_conditions)

launch_sources = types.ModuleType('launch.launch_description_sources')
launch_sources.PythonLaunchDescriptionSource = type('PythonLaunchDescriptionSource', (), {'__init__': lambda self, *args, **kwargs: None})
sys.modules.setdefault('launch.launch_description_sources', launch_sources)

launch_substitutions = types.ModuleType('launch.substitutions')
launch_substitutions.LaunchConfiguration = type('LaunchConfiguration', (), {'__init__': lambda self, name, default=None: None})
launch_substitutions.PathJoinSubstitution = type('PathJoinSubstitution', (), {'__init__': lambda self, *args, **kwargs: None})
launch_substitutions.PythonExpression = type('PythonExpression', (), {'__init__': lambda self, *args, **kwargs: None})
sys.modules.setdefault('launch.substitutions', launch_substitutions)

launch_ros_actions = types.ModuleType('launch_ros.actions')
launch_ros_actions.LifecycleNode = type('LifecycleNode', (), {'__init__': lambda self, *args, **kwargs: None})
launch_ros_actions.Node = type('Node', (), {'__init__': lambda self, *args, **kwargs: None})
sys.modules.setdefault('launch_ros.actions', launch_ros_actions)

launch_ros_substitutions = types.ModuleType('launch_ros.substitutions')
launch_ros_substitutions.FindPackageShare = type('FindPackageShare', (), {'__init__': lambda self, *args, **kwargs: None})
sys.modules.setdefault('launch_ros.substitutions', launch_ros_substitutions)

ament_packages = types.ModuleType('ament_index_python.packages')
ament_packages.get_package_share_directory = lambda name: str(ROOT / name)
sys.modules.setdefault('ament_index_python.packages', ament_packages)

from arm_bringup.launch_factory import get_runtime_lane_spec


def _reload_launch_factory(
    monkeypatch,
    *,
    backend_config: Path | None = None,
    runtime_profiles: Path | None = None,
    promotion_receipts: Path | None = None,
    evidence_file: Path | None = None,
    gate_report: Path | None = None,
):
    if backend_config is not None:
        monkeypatch.setenv('EMBODIED_ARM_PLANNING_BACKENDS_FILE', str(backend_config))
    if runtime_profiles is not None:
        monkeypatch.setenv('EMBODIED_ARM_RUNTIME_PROFILES_FILE', str(runtime_profiles))
    if promotion_receipts is not None:
        monkeypatch.setenv('EMBODIED_ARM_RUNTIME_PROMOTION_RECEIPTS_FILE', str(promotion_receipts))
    if evidence_file is not None:
        monkeypatch.setenv('EMBODIED_ARM_VALIDATED_LIVE_EVIDENCE_FILE', str(evidence_file))
    if gate_report is not None:
        monkeypatch.setenv('EMBODIED_ARM_TARGET_RUNTIME_GATE_FILE', str(gate_report))
    import arm_bringup.launch_factory as launch_factory

    return importlib.reload(launch_factory)


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


def test_real_candidate_lane_is_fail_closed_until_backend_declared() -> None:
    spec = get_runtime_lane_spec('real_candidate')
    assert spec.enable_moveit is True
    assert spec.enable_ros2_control is True
    assert spec.hardware_execution_mode == 'ros2_control_live'
    assert spec.execution_backbone == 'ros2_control'
    assert spec.execution_backbone_declared is False
    assert spec.planning_capability == 'validated_live'
    assert spec.planning_backend_name == 'validated_live_bridge'
    assert spec.planning_backend_declared is False
    assert spec.public_runtime_tier == 'preview'
    assert spec.task_workbench_visible is False
    assert spec.task_execution_interactive is False


def test_real_validated_live_lane_stays_preview_without_promotion_receipt(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / 'planning_backend_profiles.yaml'
    config.write_text(
        'validated_live_bridge:\n'
        '  plugin: http_bridge\n'
        '  declared: true\n'
        '  capability_mode: validated_live\n'
        '  planner_plugin: moveit_http_bridge\n'
        '  scene_source: runtime_scene_service\n'
        '  url: http://127.0.0.1:8088/plan\n',
        encoding='utf-8',
    )
    runtime_profiles = tmp_path / 'runtime_profiles.yaml'
    runtime_payload = yaml.safe_load((ROOT / 'arm_bringup' / 'config' / 'runtime_profiles.yaml').read_text(encoding='utf-8'))
    runtime_payload['real_validated_live']['execution_backbone_declared'] = True
    runtime_profiles.write_text(yaml.safe_dump(runtime_payload, sort_keys=False), encoding='utf-8')

    launch_factory = _reload_launch_factory(monkeypatch, backend_config=config, runtime_profiles=runtime_profiles)
    spec = launch_factory.get_runtime_lane_spec('real_validated_live')
    assert spec.planning_backend_declared is True
    assert spec.execution_backbone_declared is True
    assert spec.enable_ros2_control is True
    assert spec.public_runtime_tier == 'preview'
    assert spec.task_workbench_visible is False
    assert spec.task_execution_interactive is False


def test_real_validated_live_lane_promotes_only_with_effective_receipt(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / 'planning_backend_profiles.yaml'
    config.write_text(
        'validated_live_bridge:\n'
        '  plugin: http_bridge\n'
        '  declared: true\n'
        '  capability_mode: validated_live\n'
        '  planner_plugin: moveit_http_bridge\n'
        '  scene_source: runtime_scene_service\n'
        '  url: http://127.0.0.1:8088/plan\n',
        encoding='utf-8',
    )
    runtime_profiles = tmp_path / 'runtime_profiles.yaml'
    runtime_payload = yaml.safe_load((ROOT / 'arm_bringup' / 'config' / 'runtime_profiles.yaml').read_text(encoding='utf-8'))
    runtime_payload['real_validated_live']['execution_backbone_declared'] = True
    runtime_profiles.write_text(yaml.safe_dump(runtime_payload, sort_keys=False), encoding='utf-8')
    promotion_receipts = tmp_path / 'runtime_promotion_receipts.yaml'
    evidence_file = tmp_path / 'validated_live_evidence.yaml'
    gate_report = tmp_path / 'target_runtime_gate.json'
    _write_target_runtime_gate_report(gate_report, target_status='passed', hil_status='passed', checklist_status='passed')
    _write_validated_live_evidence(evidence_file, target_status='passed', hil_status='passed', checklist_status='passed', gate_report=gate_report)
    promotion_receipts.write_text(
        'validated_sim:\n'
        '  promoted: true\n'
        '  receipt_id: validated-sim-baseline\n'
        '  checked_by: repository-ci\n'
        '  checked_at: 2026-04-08T00:00:00Z\n'
        '  required_evidence: [backend-active, gateway, contract-artifacts, runtime-contracts]\n'
        '  evidence: [backend-active, gateway, contract-artifacts, runtime-contracts]\n'
        'validated_live:\n'
        '  promoted: true\n'
        '  receipt_id: live-promoted-001\n'
        '  checked_by: release-bot\n'
        '  checked_at: 2026-04-09T00:00:00Z\n'
        '  required_evidence: [validated_live_backbone_declared, target_runtime_gate_passed, hil_gate_passed, release_checklist_signed]\n'
        '  evidence: [validated_live_backbone_declared, target_runtime_gate_passed, hil_gate_passed, release_checklist_signed]\n',
        encoding='utf-8',
    )

    launch_factory = _reload_launch_factory(
        monkeypatch,
        backend_config=config,
        runtime_profiles=runtime_profiles,
        promotion_receipts=promotion_receipts,
        evidence_file=evidence_file,
        gate_report=gate_report,
    )
    spec = launch_factory.get_runtime_lane_spec('real_validated_live')
    assert spec.planning_backend_declared is True
    assert spec.execution_backbone_declared is True
    assert spec.enable_ros2_control is True
    assert spec.public_runtime_tier == 'validated_live'
    assert spec.task_workbench_visible is True
    assert spec.task_execution_interactive is True


def test_real_validated_live_lane_stays_preview_when_hil_evidence_not_passed(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / 'planning_backend_profiles.yaml'
    config.write_text(
        """validated_live_bridge:
  plugin: http_bridge
  declared: true
  capability_mode: validated_live
  planner_plugin: moveit_http_bridge
  scene_source: runtime_scene_service
  url: http://127.0.0.1:8088/plan
""",
        encoding='utf-8',
    )
    runtime_profiles = tmp_path / 'runtime_profiles.yaml'
    runtime_payload = yaml.safe_load((ROOT / 'arm_bringup' / 'config' / 'runtime_profiles.yaml').read_text(encoding='utf-8'))
    runtime_payload['real_validated_live']['execution_backbone_declared'] = True
    runtime_profiles.write_text(yaml.safe_dump(runtime_payload, sort_keys=False), encoding='utf-8')
    promotion_receipts = tmp_path / 'runtime_promotion_receipts.yaml'
    evidence_file = tmp_path / 'validated_live_evidence.yaml'
    gate_report = tmp_path / 'target_runtime_gate.json'
    _write_target_runtime_gate_report(gate_report, target_status='passed', hil_status='blocked', checklist_status='passed')
    _write_validated_live_evidence(evidence_file, target_status='passed', hil_status='not_executed', checklist_status='passed', gate_report=gate_report)
    promotion_receipts.write_text(
        """validated_live:
  promoted: true
  receipt_id: live-promoted-001
  checked_by: release-bot
  checked_at: 2026-04-09T00:00:00Z
  required_evidence: [validated_live_backbone_declared, target_runtime_gate_passed, hil_gate_passed, release_checklist_signed]
  evidence: [validated_live_backbone_declared, target_runtime_gate_passed, hil_gate_passed, release_checklist_signed]
""",
        encoding='utf-8',
    )

    launch_factory = _reload_launch_factory(
        monkeypatch,
        backend_config=config,
        runtime_profiles=runtime_profiles,
        promotion_receipts=promotion_receipts,
        evidence_file=evidence_file,
        gate_report=gate_report,
    )
    spec = launch_factory.get_runtime_lane_spec('real_validated_live')
    assert spec.public_runtime_tier == 'preview'
    assert spec.task_workbench_visible is False
    assert spec.task_execution_interactive is False


def test_real_validated_live_lane_stays_preview_with_incomplete_live_receipt(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / 'planning_backend_profiles.yaml'
    config.write_text(
        """validated_live_bridge:
  plugin: http_bridge
  declared: true
  capability_mode: validated_live
  planner_plugin: moveit_http_bridge
  scene_source: runtime_scene_service
  url: http://127.0.0.1:8088/plan
""",
        encoding='utf-8',
    )
    runtime_profiles = tmp_path / 'runtime_profiles.yaml'
    runtime_payload = yaml.safe_load((ROOT / 'arm_bringup' / 'config' / 'runtime_profiles.yaml').read_text(encoding='utf-8'))
    runtime_payload['real_validated_live']['execution_backbone_declared'] = True
    runtime_profiles.write_text(yaml.safe_dump(runtime_payload, sort_keys=False), encoding='utf-8')
    promotion_receipts = tmp_path / 'runtime_promotion_receipts.yaml'
    evidence_file = tmp_path / 'validated_live_evidence.yaml'
    gate_report = tmp_path / 'target_runtime_gate.json'
    _write_target_runtime_gate_report(gate_report, target_status='passed', hil_status='passed', checklist_status='blocked')
    _write_validated_live_evidence(evidence_file, target_status='passed', hil_status='passed', checklist_status='not_signed', gate_report=gate_report)
    promotion_receipts.write_text(
        """validated_live:
  promoted: true
  receipt_id: live-promoted-001
  checked_by: release-bot
  checked_at: 2026-04-09T00:00:00Z
  required_evidence: [validated_live_backbone_declared, target_runtime_gate_passed]
  evidence: [validated_live_backbone_declared]
""",
        encoding='utf-8',
    )

    launch_factory = _reload_launch_factory(
        monkeypatch,
        backend_config=config,
        runtime_profiles=runtime_profiles,
        promotion_receipts=promotion_receipts,
        evidence_file=evidence_file,
        gate_report=gate_report,
    )
    spec = launch_factory.get_runtime_lane_spec('real_validated_live')
    assert spec.public_runtime_tier == 'preview'
    assert spec.task_workbench_visible is False
    assert spec.task_execution_interactive is False


def test_missing_runtime_profiles_file_fails_fast(monkeypatch, tmp_path: Path) -> None:
    missing_runtime_profiles = tmp_path / 'missing_runtime_profiles.yaml'
    monkeypatch.setenv('EMBODIED_ARM_RUNTIME_PROFILES_FILE', str(missing_runtime_profiles))
    monkeypatch.delenv('EMBODIED_ARM_ALLOW_GENERATED_FALLBACK', raising=False)
    import arm_bringup.launch_factory as launch_factory

    launch_factory = importlib.reload(launch_factory)
    try:
        launch_factory.get_runtime_lane_spec('validated_sim')
    except RuntimeError as exc:
        assert 'runtime profiles file missing or yaml unavailable' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('missing runtime profile artifact must fail fast')


def test_real_authoritative_alias_resolves_to_real_candidate() -> None:
    candidate = get_runtime_lane_spec('real_candidate')
    alias = get_runtime_lane_spec('real_authoritative')
    assert alias == candidate
