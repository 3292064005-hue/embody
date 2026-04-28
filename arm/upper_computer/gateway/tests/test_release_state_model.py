from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_state_model import build_release_gate_report


def _write_repo_summary(root: Path, *, overall_status: str = 'passed', step_statuses: dict[str, str] | None = None) -> None:
    artifact_dir = root / 'artifacts' / 'repository_validation' / 'repo'
    artifact_dir.mkdir(parents=True, exist_ok=True)
    statuses = step_statuses or {
        'backend-active': 'passed',
        'contract-artifacts': 'passed',
        'runtime-contracts': 'passed',
        'gateway': 'passed',
        'frontend-typecheck-app': 'passed',
        'frontend-build': 'passed',
        'audit': 'passed',
    }
    for name in statuses:
        (artifact_dir / f'{name}.log').write_text('ok', encoding='utf-8')
    (artifact_dir / 'verification_summary.json').write_text(
        json.dumps(
            {
                'profile': 'repo',
                'overallStatus': overall_status,
                'requiredSteps': list(statuses.keys()),
                'stepStatuses': statuses,
            },
            indent=2,
        ),
        encoding='utf-8',
    )


def _write_gate_report(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _write_target_runtime_gate(root: Path, *, target: str = 'passed', hil: str = 'passed', checklist: str = 'passed', release: str = 'passed') -> None:
    _write_gate_report(
        root / 'artifacts' / 'release_gates' / 'target_runtime_gate.json',
        {
            'targetGate': target,
            'hilGate': hil,
            'releaseChecklistGate': checklist,
            'releaseGate': release,
        },
    )


def _write_validated_live_aux_reports(root: Path, *, hil: str = 'passed', checklist: str = 'passed') -> None:
    _write_gate_report(
        root / 'artifacts' / 'release_gates' / 'validated_live_hil_gate.json',
        {'hilGate': hil, 'status': hil},
    )
    _write_gate_report(
        root / 'artifacts' / 'release_gates' / 'validated_live_release_checklist_gate.json',
        {'releaseChecklistGate': checklist, 'status': checklist},
    )


def _write_validated_live_evidence(
    root: Path,
    *,
    hil_status: str = 'passed',
    checklist_status: str = 'passed',
    hil_doc: str | None = None,
    checklist_doc: str | None = None,
    gate_hil: str | None = None,
    gate_checklist: str | None = None,
) -> None:
    evidence_dir = root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = root / 'docs' / 'evidence' / 'validated_live'
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / 'hil_smoke_report.md').write_text(
        hil_doc
        or '# HIL smoke report\n\n> Status: evidence\n> Gate marker: `hil_gate_passed`\n\n- Status: **PASSED**\n- Source of truth: `artifacts/release_gates/validated_live_hil_gate.json`\n',
        encoding='utf-8',
    )
    (docs_dir / 'release_checklist.md').write_text(
        checklist_doc
        or '# Release checklist sign-off\n\n> Status: evidence\n> Gate marker: `release_checklist_signed`\n\n- Status: **PASSED**\n- Source of truth: `artifacts/release_gates/validated_live_release_checklist_gate.json`\n',
        encoding='utf-8',
    )
    effective_hil = gate_hil or hil_status
    effective_checklist = gate_checklist or checklist_status
    _write_validated_live_aux_reports(root, hil=effective_hil, checklist=effective_checklist)
    _write_target_runtime_gate(
        root,
        hil=effective_hil,
        checklist=effective_checklist,
        release='passed' if effective_hil == 'passed' and effective_checklist == 'passed' else 'blocked',
    )
    (evidence_dir / 'validated_live_evidence.yaml').write_text(
        (
            'schema_version: 2\n'
            'evidence:\n'
            f'  hil_gate_passed:\n'
            f'    status: {hil_status}\n'
            '    artifact: docs/evidence/validated_live/hil_smoke_report.md\n'
            '    gate_field: hilGate\n'
            '    gate_report: artifacts/release_gates/validated_live_hil_gate.json\n'
            f'  release_checklist_signed:\n'
            f'    status: {checklist_status}\n'
            '    artifact: docs/evidence/validated_live/release_checklist.md\n'
            '    gate_field: releaseChecklistGate\n'
            '    gate_report: artifacts/release_gates/validated_live_release_checklist_gate.json\n'
        ),
        encoding='utf-8',
    )


def test_release_gate_report_overrides_conflicting_gate_inputs(tmp_path: Path) -> None:
    _write_repo_summary(tmp_path)
    _write_validated_live_evidence(tmp_path)

    report = build_release_gate_report(
        {},
        {
            'repo_gate': 'blocked',
            'env': 'passed',
            'ros_build': 'passed',
            'ros_smoke': 'passed',
            'negative_path_subset': 'passed',
            'runtime_baseline': 'passed',
            'target_gate': 'blocked',
            'hil': 'passed',
            'release_checklist': 'blocked',
        },
        root=tmp_path,
    )

    assert report['repoGate'] == 'passed'
    assert report['targetGate'] == 'passed'
    assert report['releaseChecklistGate'] == 'passed'
    assert report['steps']['repo_gate'] == 'passed'
    assert report['steps']['target_gate'] == 'passed'
    assert report['steps']['release_checklist'] == 'passed'
    assert report['hasBlockingStep'] is False
    assert report['blockingSteps'] == {}


def test_release_gate_requires_repo_summary_not_just_logs(tmp_path: Path) -> None:
    artifact_dir = tmp_path / 'artifacts' / 'repository_validation' / 'repo'
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / 'backend-active.log').write_text('ok', encoding='utf-8')

    report = build_release_gate_report(
        {},
        {'env': 'passed', 'ros_build': 'passed', 'ros_smoke': 'passed', 'negative_path_subset': 'passed', 'hil': 'passed'},
        root=tmp_path,
    )

    assert report['repoGate'] == 'not_executed'
    assert report['releaseGate'] == 'blocked'


def test_release_gate_can_reach_passed_when_target_hil_and_checklist_evidence_all_pass(tmp_path: Path) -> None:
    _write_repo_summary(tmp_path)
    _write_validated_live_evidence(tmp_path)

    report = build_release_gate_report(
        {},
        {'env': 'passed', 'ros_build': 'passed', 'ros_smoke': 'passed', 'negative_path_subset': 'passed', 'runtime_baseline': 'passed'},
        root=tmp_path,
    )

    assert report['repoGate'] == 'passed'
    assert report['targetGate'] == 'passed'
    assert report['hilGate'] == 'passed'
    assert report['releaseChecklistGate'] == 'passed'
    assert report['releaseGate'] == 'passed'
    assert report['steps']['release_gate'] == 'passed'


def test_release_gate_can_bootstrap_without_preexisting_target_runtime_gate(tmp_path: Path) -> None:
    _write_repo_summary(tmp_path)
    _write_validated_live_evidence(tmp_path)
    (tmp_path / 'artifacts' / 'release_gates' / 'target_runtime_gate.json').unlink()

    report = build_release_gate_report(
        {},
        {'env': 'passed', 'ros_build': 'passed', 'ros_smoke': 'passed', 'negative_path_subset': 'passed', 'runtime_baseline': 'passed'},
        root=tmp_path,
    )

    assert report['targetGate'] == 'passed'
    assert report['hilGate'] == 'passed'
    assert report['releaseChecklistGate'] == 'passed'
    assert report['releaseGate'] == 'passed'


def test_release_gate_blocks_placeholder_hil_and_checklist_evidence(tmp_path: Path) -> None:
    _write_repo_summary(tmp_path)
    _write_validated_live_evidence(tmp_path, hil_doc='hil ok', checklist_doc='signed')

    report = build_release_gate_report(
        {},
        {'env': 'passed', 'ros_build': 'passed', 'ros_smoke': 'passed', 'negative_path_subset': 'passed', 'runtime_baseline': 'passed'},
        root=tmp_path,
    )

    assert report['hilGate'] == 'blocked'
    assert report['releaseChecklistGate'] == 'blocked'
    assert report['releaseGate'] == 'blocked'


def test_release_gate_target_requires_runtime_baseline_step(tmp_path: Path) -> None:
    _write_repo_summary(tmp_path)
    _write_validated_live_evidence(tmp_path)

    report = build_release_gate_report(
        {},
        {'env': 'passed', 'ros_build': 'passed', 'ros_smoke': 'passed', 'negative_path_subset': 'passed', 'runtime_baseline': 'not_executed'},
        root=tmp_path,
    )

    assert report['targetGate'] == 'blocked'
    assert report['releaseGate'] == 'blocked'


def test_release_gate_reports_blocked_when_repo_summary_is_blocked(tmp_path: Path) -> None:
    _write_repo_summary(
        tmp_path,
        overall_status='blocked',
        step_statuses={
            'backend-active': 'passed',
            'contract-artifacts': 'passed',
            'runtime-contracts': 'passed',
            'gateway': 'passed',
            'frontend-typecheck-app': 'passed',
            'frontend-build': 'passed',
            'frontend-e2e': 'skipped',
            'audit': 'passed',
        },
    )

    report = build_release_gate_report(
        {},
        {'env': 'passed', 'ros_build': 'passed', 'ros_smoke': 'passed', 'negative_path_subset': 'passed', 'runtime_baseline': 'passed'},
        root=tmp_path,
    )

    assert report['repoGate'] == 'blocked'
    assert report['releaseGate'] == 'blocked'
    assert report['steps']['repo_gate'] == 'blocked'
