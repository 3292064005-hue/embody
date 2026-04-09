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


def test_release_gate_report_overrides_conflicting_gate_inputs(tmp_path: Path) -> None:
    _write_repo_summary(tmp_path)

    evidence_dir = tmp_path / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = tmp_path / 'docs' / 'evidence' / 'validated_live'
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / 'release_checklist.md').write_text('signed', encoding='utf-8')
    (docs_dir / 'hil_smoke_report.md').write_text('hil ok', encoding='utf-8')
    (evidence_dir / 'validated_live_evidence.yaml').write_text(
        """schema_version: 2
evidence:
  hil_gate_passed:
    status: passed
    artifact: docs/evidence/validated_live/hil_smoke_report.md
  release_checklist_signed:
    status: passed
    artifact: docs/evidence/validated_live/release_checklist.md
""",
        encoding='utf-8',
    )

    report = build_release_gate_report(
        {},
        {
            'repo_gate': 'blocked',
            'env': 'passed',
            'ros_build': 'passed',
            'ros_smoke': 'passed',
            'negative_path_subset': 'passed',
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

    evidence_dir = tmp_path / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = tmp_path / 'docs' / 'evidence' / 'validated_live'
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / 'hil_smoke_report.md').write_text('hil ok', encoding='utf-8')
    (docs_dir / 'release_checklist.md').write_text('signed', encoding='utf-8')
    (evidence_dir / 'validated_live_evidence.yaml').write_text(
        """schema_version: 2
evidence:
  hil_gate_passed:
    status: passed
    artifact: docs/evidence/validated_live/hil_smoke_report.md
  release_checklist_signed:
    status: passed
    artifact: docs/evidence/validated_live/release_checklist.md
""",
        encoding='utf-8',
    )

    report = build_release_gate_report(
        {},
        {'env': 'passed', 'ros_build': 'passed', 'ros_smoke': 'passed', 'negative_path_subset': 'passed'},
        root=tmp_path,
    )

    assert report['repoGate'] == 'passed'
    assert report['targetGate'] == 'passed'
    assert report['hilGate'] == 'passed'
    assert report['releaseChecklistGate'] == 'passed'
    assert report['releaseGate'] == 'passed'
    assert report['steps']['release_gate'] == 'passed'
