from __future__ import annotations

import json
from pathlib import Path

from scripts import write_frontend_validation_status as frontend_status
from runtime_authority import build_validated_live_governance_ledger


def test_frontend_validation_ledger_aggregates_repository_summary(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    artifacts = root / 'artifacts'
    repo_validation = artifacts / 'repository_validation' / 'repo'
    repo_validation.mkdir(parents=True)
    package_json = root / 'frontend' / 'package.json'
    package_json.parent.mkdir(parents=True)
    package_json.write_text(
        json.dumps({'engines': {'node': '>=22 <23'}, 'packageManager': 'npm@10.9.2'}),
        encoding='utf-8',
    )
    summary = {
        'profile': 'repo',
        'generatedAt': '2026-04-20T00:00:00Z',
        'stepStatuses': {
            'frontend-deps': 'passed',
            'frontend-typecheck-app': 'passed',
            'frontend-typecheck-test': 'passed',
            'frontend-unit': 'failed',
            'frontend-build': 'not_executed',
            'frontend-e2e': 'not_executed',
        },
        'logs': {
            'frontend-deps': 'frontend-deps.log',
            'frontend-typecheck-app': 'frontend-typecheck-app.log',
            'frontend-typecheck-test': 'frontend-typecheck-test.log',
            'frontend-unit': 'frontend-unit.log',
            'frontend-build': 'frontend-build.log',
            'frontend-e2e': 'frontend-e2e.log',
        },
    }
    (repo_validation / 'verification_summary.json').write_text(json.dumps(summary), encoding='utf-8')
    for name in summary['logs'].values():
        (repo_validation / name).write_text('log', encoding='utf-8')

    monkeypatch.setattr(frontend_status, 'ROOT', root)
    monkeypatch.setattr(frontend_status, 'ARTIFACTS', artifacts)
    monkeypatch.setattr(frontend_status, 'REPO_VALIDATION', artifacts / 'repository_validation')
    monkeypatch.setattr(frontend_status, 'LEDGER_PATH', artifacts / 'release_gates' / 'frontend_validation_ledger.json')
    monkeypatch.setattr(frontend_status, 'DOC_PATH', root / 'docs' / 'evidence' / 'frontend-validation-status.md')
    monkeypatch.setattr(frontend_status, 'PACKAGE_JSON', package_json)

    ledger = frontend_status.build_frontend_validation_ledger()
    assert ledger['overallStatus'] == 'failed'
    assert ledger['generatedAt'] == '2026-04-20T00:00:00Z'
    assert ledger['sourceProfile'] == 'repo'
    assert ledger['environment']['buildProfile'] == 'unknown'
    assert len(ledger['matrix']) == 6
    markdown = frontend_status.build_frontend_validation_markdown(ledger)
    assert '| Step | Group | Status | Required | Blocking Class | Log |' in markdown
    assert '`failed`' in markdown


def test_frontend_validation_ledger_prefers_repository_validation_summary_over_packaged_copy_when_present(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    artifacts = root / 'artifacts'
    packaged = artifacts / 'release_gates' / 'frontend_validation_artifacts'
    repo_validation = artifacts / 'repository_validation' / 'repo'
    packaged.mkdir(parents=True)
    repo_validation.mkdir(parents=True)
    package_json = root / 'frontend' / 'package.json'
    package_json.parent.mkdir(parents=True)
    package_json.write_text(json.dumps({'engines': {'node': '>=22 <23'}, 'packageManager': 'npm@10.9.2'}), encoding='utf-8')
    repo_validation.joinpath('verification_summary.json').write_text(json.dumps({'profile': 'repo', 'stepStatuses': {'frontend-unit': 'failed'}, 'logs': {'frontend-unit': 'frontend-unit.log'}}), encoding='utf-8')
    summary = {
        'profile': 'release_gates',
        'generatedAt': '2026-04-20T01:02:03Z',
        'stepStatuses': {
            'frontend-deps': 'passed',
            'frontend-typecheck-app': 'passed',
            'frontend-typecheck-test': 'passed',
            'frontend-unit': 'passed',
            'frontend-build': 'passed',
            'frontend-e2e': 'passed',
        },
        'logs': {step: f'{step}.log' for step in [
            'frontend-deps',
            'frontend-typecheck-app',
            'frontend-typecheck-test',
            'frontend-unit',
            'frontend-build',
            'frontend-e2e',
        ]},
    }
    packaged.joinpath('verification_summary.json').write_text(json.dumps(summary), encoding='utf-8')
    for name in summary['logs'].values():
        payload = '[build-guard] buildProfile=release mockEnabled=false mockMode=off\n' if name == 'frontend-build.log' else 'log'
        packaged.joinpath(name).write_text(payload, encoding='utf-8')

    monkeypatch.setattr(frontend_status, 'ROOT', root)
    monkeypatch.setattr(frontend_status, 'ARTIFACTS', artifacts)
    monkeypatch.setattr(frontend_status, 'REPO_VALIDATION', artifacts / 'repository_validation')
    monkeypatch.setattr(frontend_status, 'LEDGER_PATH', artifacts / 'release_gates' / 'frontend_validation_ledger.json')
    monkeypatch.setattr(frontend_status, 'DOC_PATH', root / 'docs' / 'evidence' / 'frontend-validation-status.md')
    monkeypatch.setattr(frontend_status, 'PACKAGE_JSON', package_json)

    ledger = frontend_status.build_frontend_validation_ledger()
    assert ledger['sourceProfile'] == 'repo'
    assert ledger['sourceSummary'] == 'artifacts/repository_validation/repo/verification_summary.json'
    assert ledger['overallStatus'] == 'failed'
    assert ledger['environment']['buildProfile'] == 'unknown'


def test_validated_live_governance_ledger_promotes_automatically_when_evidence_is_effective() -> None:
    ledger = build_validated_live_governance_ledger()
    assert ledger['backbone']['lane'] == 'real_validated_live'
    assert ledger['promotion']['effective'] is True
    assert ledger['promotion']['mode'] == 'automatic_when_ready'
    assert ledger['promotion']['missingEvidence'] == []


def test_frontend_validation_ledger_marks_skipped_e2e_as_blocked(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    artifacts = root / 'artifacts'
    manual_validation = artifacts / 'repository_validation' / 'release_gates'
    manual_validation.mkdir(parents=True)
    package_json = root / 'frontend' / 'package.json'
    package_json.parent.mkdir(parents=True)
    package_json.write_text(json.dumps({'engines': {'node': '>=22 <23'}, 'packageManager': 'npm@10.9.2'}), encoding='utf-8')
    summary = {
        'profile': 'release_gates',
        'generatedAt': '2026-04-20T01:02:03Z',
        'stepStatuses': {
            'frontend-deps': 'passed',
            'frontend-typecheck-app': 'passed',
            'frontend-typecheck-test': 'passed',
            'frontend-unit': 'passed',
            'frontend-build': 'passed',
            'frontend-e2e': 'skipped',
        },
        'logs': {step: f'{step}.log' for step in [
            'frontend-deps',
            'frontend-typecheck-app',
            'frontend-typecheck-test',
            'frontend-unit',
            'frontend-build',
            'frontend-e2e',
        ]},
    }
    manual_validation.joinpath('verification_summary.json').write_text(json.dumps(summary), encoding='utf-8')
    for name in summary['logs'].values():
        payload = '[frontend:e2e] skipped: no usable Chromium executable is available.\n' if name == 'frontend-e2e.log' else 'log'
        manual_validation.joinpath(name).write_text(payload, encoding='utf-8')

    monkeypatch.setattr(frontend_status, 'ROOT', root)
    monkeypatch.setattr(frontend_status, 'ARTIFACTS', artifacts)
    monkeypatch.setattr(frontend_status, 'REPO_VALIDATION', artifacts / 'repository_validation')
    monkeypatch.setattr(frontend_status, 'LEDGER_PATH', artifacts / 'release_gates' / 'frontend_validation_ledger.json')
    monkeypatch.setattr(frontend_status, 'DOC_PATH', root / 'docs' / 'evidence' / 'frontend-validation-status.md')
    monkeypatch.setattr(frontend_status, 'PACKAGE_JSON', package_json)

    ledger = frontend_status.build_frontend_validation_ledger()
    assert ledger['overallStatus'] == 'blocked'
    e2e = next(item for item in ledger['matrix'] if item['step'] == 'frontend-e2e')
    assert e2e['status'] == 'skipped'
    assert e2e['blockingClass'] == 'infrastructure'
    assert ledger['environment']['environmentReady'] is False



def test_frontend_validation_render_outputs_normalizes_packaged_summary_for_non_release_build(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    artifacts = root / 'artifacts'
    packaged = artifacts / 'release_gates' / 'frontend_validation_artifacts'
    packaged.mkdir(parents=True)
    package_json = root / 'frontend' / 'package.json'
    package_json.parent.mkdir(parents=True)
    package_json.write_text(json.dumps({'engines': {'node': '>=22 <23'}, 'packageManager': 'npm@10.9.2'}), encoding='utf-8')
    summary = {
        'profile': 'release_gates',
        'generatedAt': '2026-04-20T01:02:03Z',
        'stepStatuses': {
            'frontend-deps': 'passed',
            'frontend-typecheck-app': 'passed',
            'frontend-typecheck-test': 'passed',
            'frontend-unit': 'passed',
            'frontend-build': 'passed',
            'frontend-e2e': 'passed',
        },
        'logs': {step: f'{step}.log' for step in [
            'frontend-deps',
            'frontend-typecheck-app',
            'frontend-typecheck-test',
            'frontend-unit',
            'frontend-build',
            'frontend-e2e',
        ]},
    }
    packaged.joinpath('verification_summary.json').write_text(json.dumps(summary), encoding='utf-8')
    for name in summary['logs'].values():
        payload = '[build-guard] buildProfile=development mockEnabled=false mockMode=off\n' if name == 'frontend-build.log' else 'log'
        packaged.joinpath(name).write_text(payload, encoding='utf-8')

    monkeypatch.setattr(frontend_status, 'ROOT', root)
    monkeypatch.setattr(frontend_status, 'ARTIFACTS', artifacts)
    monkeypatch.setattr(frontend_status, 'REPO_VALIDATION', artifacts / 'repository_validation')
    monkeypatch.setattr(frontend_status, 'LEDGER_PATH', artifacts / 'release_gates' / 'frontend_validation_ledger.json')
    monkeypatch.setattr(frontend_status, 'DOC_PATH', root / 'docs' / 'evidence' / 'frontend-validation-status.md')
    monkeypatch.setattr(frontend_status, 'PACKAGE_JSON', package_json)

    outputs = frontend_status.render_outputs()
    packaged_summary = json.loads(outputs[artifacts / 'release_gates' / 'frontend_validation_artifacts' / 'verification_summary.json'])
    assert packaged_summary['stepStatuses']['frontend-build'] == 'blocked'
    assert packaged_summary['overallStatus'] == 'blocked'
