from __future__ import annotations

import json
from pathlib import Path

from scripts import verify_frontend_validation as frontend_verify


def test_verify_frontend_validation_writes_summary_with_frontend_step_names(tmp_path: Path, monkeypatch) -> None:
    artifact_dir = tmp_path / 'artifacts' / 'repository_validation' / frontend_verify.PROFILE
    monkeypatch.setattr(frontend_verify, 'ROOT_DIR', tmp_path)

    fake_steps = [
        ('frontend-deps', ['echo', 'deps'], tmp_path, None),
        ('frontend-typecheck-app', ['echo', 'typecheck'], tmp_path, None),
    ]
    monkeypatch.setattr(frontend_verify, 'build_frontend_steps', lambda: fake_steps)
    monkeypatch.setattr(frontend_verify, 'clean_hygiene_residue', lambda: None)
    monkeypatch.setattr(frontend_verify, 'run_step', lambda name, command, cwd, env, artifact_dir: 0)

    assert frontend_verify.main([]) == 0
    summary = json.loads((artifact_dir / 'verification_summary.json').read_text(encoding='utf-8'))
    assert summary['profile'] == frontend_verify.PROFILE
    assert 'generatedAt' in summary
    assert summary['overallStatus'] == 'passed'
    assert summary['stepStatuses']['frontend-deps'] == 'passed'
    assert summary['stepStatuses']['frontend-typecheck-app'] == 'passed'


def test_verify_frontend_validation_records_skipped_e2e_status(tmp_path: Path, monkeypatch) -> None:
    artifact_dir = tmp_path / 'artifacts' / 'repository_validation' / frontend_verify.PROFILE
    monkeypatch.setattr(frontend_verify, 'ROOT_DIR', tmp_path)

    fake_steps = [('frontend-e2e', ['echo', 'e2e'], tmp_path, None)]
    monkeypatch.setattr(frontend_verify, 'build_frontend_steps', lambda: fake_steps)
    monkeypatch.setattr(frontend_verify, 'clean_hygiene_residue', lambda: None)

    def fake_run_step(name, command, cwd, env, artifact_dir):
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / f'{name}.log').write_text('[frontend:e2e] skipped: no usable Chromium executable is available.\n', encoding='utf-8')
        return 0

    monkeypatch.setattr(frontend_verify, 'run_step', fake_run_step)

    assert frontend_verify.main([]) == 0
    summary = json.loads((artifact_dir / 'verification_summary.json').read_text(encoding='utf-8'))
    assert summary['overallStatus'] == 'blocked'
    assert summary['stepStatuses']['frontend-e2e'] == 'skipped'
