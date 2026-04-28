from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts'
for entry in (ROOT, SCRIPTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.final_audit import audit_frontend_validation_evidence, audit_release_gate_consistency, audit_release_manifest, audit_repository_hygiene


def test_repository_hygiene_ignores_cache_artifacts_excluded_from_release(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    (root / 'frontend').mkdir(parents=True)
    cache_dir = root / 'scripts' / '__pycache__'
    cache_dir.mkdir(parents=True)
    (cache_dir / 'x.pyc').write_bytes(b'0')
    monkeypatch.setattr('scripts.final_audit.ROOT', root)
    issues = audit_repository_hygiene()
    assert not [issue for issue in issues if '__pycache__' in issue or '.pyc' in issue]


import json


def test_frontend_validation_audit_flags_skipped_e2e_marked_as_passed(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    (root / 'artifacts' / 'release_gates').mkdir(parents=True)
    (root / 'docs' / 'evidence').mkdir(parents=True)
    log_dir = root / 'artifacts' / 'repository_validation' / 'frontend_manual'
    log_dir.mkdir(parents=True)
    (log_dir / 'frontend-e2e.log').write_text('[frontend:e2e] skipped: no usable Chromium executable is available.\n', encoding='utf-8')
    ledger = {
        'overallStatus': 'passed',
        'matrix': [
            {'step': 'frontend-deps', 'status': 'passed', 'logPath': 'artifacts/repository_validation/frontend_manual/frontend-deps.log', 'logExists': False},
            {'step': 'frontend-typecheck-app', 'status': 'passed', 'logPath': 'artifacts/repository_validation/frontend_manual/frontend-typecheck-app.log', 'logExists': False},
            {'step': 'frontend-typecheck-test', 'status': 'passed', 'logPath': 'artifacts/repository_validation/frontend_manual/frontend-typecheck-test.log', 'logExists': False},
            {'step': 'frontend-unit', 'status': 'passed', 'logPath': 'artifacts/repository_validation/frontend_manual/frontend-unit.log', 'logExists': False},
            {'step': 'frontend-build', 'status': 'passed', 'logPath': 'artifacts/repository_validation/frontend_manual/frontend-build.log', 'logExists': False},
            {'step': 'frontend-e2e', 'status': 'passed', 'blockingClass': 'none', 'logPath': 'artifacts/repository_validation/frontend_manual/frontend-e2e.log', 'logExists': True},
        ],
    }
    ledger['environment'] = {'playwrightBrowserContract': 'chromium preinstalled via CI or PLAYWRIGHT_CHROMIUM_EXECUTABLE'}
    (root / 'artifacts' / 'release_gates' / 'frontend_validation_ledger.json').write_text(json.dumps(ledger), encoding='utf-8')
    (root / 'docs' / 'evidence' / 'frontend-validation-status.md').write_text('Machine-readable ledger\n| Step | Group | Status | Required | Log |\n../../artifacts/release_gates/frontend_validation_ledger.json\n', encoding='utf-8')

    monkeypatch.setattr('scripts.final_audit.ROOT', root)
    monkeypatch.setattr('scripts.final_audit.check_frontend_validation_outputs', lambda: [])
    issues = audit_frontend_validation_evidence()
    assert any('non-skipped' in issue for issue in issues)


def test_release_manifest_audit_flags_drift(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    (root / 'scripts').mkdir(parents=True)
    (root / 'artifacts').mkdir(parents=True)
    (root / 'artifacts' / 'release_manifest.json').write_text(json.dumps({'fileCount': 0, 'files': []}), encoding='utf-8')
    package_release = root / 'scripts' / 'package_release.py'
    package_release.write_text(
        'from pathlib import Path\n'
        'import json\n'
        'ROOT = Path(__file__).resolve().parents[1]\n'
        'MANIFEST_OUTPUT = ROOT / "artifacts" / "release_manifest.json"\n'
        'def check_manifest(manifest_path=MANIFEST_OUTPUT, root=ROOT):\n'
        '    payload = json.loads(manifest_path.read_text(encoding="utf-8"))\n'
        '    return [] if payload.get("files") == ["keep.txt"] else ["release manifest drift detected"]\n',
        encoding='utf-8',
    )
    monkeypatch.setattr('scripts.final_audit.ROOT', root)
    issues = audit_release_manifest()
    assert 'release manifest drift detected' in issues


def test_release_gate_audit_flags_drift_between_gate_and_evidence(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    (root / 'artifacts' / 'release_gates').mkdir(parents=True)
    (root / 'artifacts' / 'repository_validation' / 'repo').mkdir(parents=True)
    (root / 'docs' / 'evidence' / 'validated_live').mkdir(parents=True)
    (root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config').mkdir(parents=True)
    repo_summary = {
        'profile': 'repo',
        'overallStatus': 'blocked',
        'requiredSteps': ['frontend-build'],
        'stepStatuses': {'frontend-build': 'blocked'},
    }
    (root / 'artifacts' / 'repository_validation' / 'repo' / 'verification_summary.json').write_text(json.dumps(repo_summary), encoding='utf-8')
    (root / 'artifacts' / 'release_gates' / 'target_runtime_gate.json').write_text(json.dumps({'repoGate': 'passed', 'targetGate': 'passed', 'hilGate': 'passed', 'releaseChecklistGate': 'passed', 'releaseGate': 'passed'}), encoding='utf-8')
    (root / 'artifacts' / 'release_gates' / 'frontend_validation_ledger.json').write_text(json.dumps({'overallStatus': 'blocked'}), encoding='utf-8')
    (root / 'docs' / 'evidence' / 'validated_live' / 'hil_smoke_report.md').write_text('Status: PASSED\n', encoding='utf-8')
    (root / 'docs' / 'evidence' / 'validated_live' / 'release_checklist.md').write_text('Status: SIGNED\n', encoding='utf-8')
    (root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'validated_live_evidence.yaml').write_text(
        'schema_version: 2\n'
        'evidence:\n'
        '  hil_gate_passed:\n'
        '    status: passed\n'
        '    artifact: docs/evidence/validated_live/hil_smoke_report.md\n'
        '  release_checklist_signed:\n'
        '    status: passed\n'
        '    artifact: docs/evidence/validated_live/release_checklist.md\n',
        encoding='utf-8',
    )
    (root / 'artifacts' / 'release_gates' / 'release_evidence.json').write_text(json.dumps({'gateSummary': {'releaseGate': 'passed'}, 'evidence': []}), encoding='utf-8')

    monkeypatch.setattr('scripts.final_audit.ROOT', root)
    monkeypatch.setattr('scripts.final_audit.VALIDATED_LIVE_EVIDENCE', root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'validated_live_evidence.yaml')
    monkeypatch.setattr('scripts.final_audit.RUNTIME_PROMOTION_RECEIPTS', root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'runtime_promotion_receipts.yaml')
    (root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'runtime_promotion_receipts.yaml').write_text('validated_live: {}\n', encoding='utf-8')

    issues = audit_release_gate_consistency()
    assert any('target_runtime_gate.json drift' in issue for issue in issues)
    assert any('release_evidence.json gateSummary drift' in issue for issue in issues)
