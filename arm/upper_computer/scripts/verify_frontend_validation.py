#!/usr/bin/env python3
from __future__ import annotations

"""Execute the standardized frontend validation lane and emit auditable logs.

This script runs the same frontend steps used by repository verification while
writing a standardized ``release_gates`` verification summary under
``artifacts/repository_validation`` so release evidence no longer depends on
the historical ``frontend_manual`` profile.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.verify_repository import build_steps, clean_hygiene_residue, run_step

PROFILE = 'release_gates'


def build_frontend_steps():
    return [step for step in build_steps('repo') if step[0].startswith('frontend-')]


def _classify_frontend_step_status(name: str, rc: int, artifact_dir: Path) -> str:
    log_path = artifact_dir / f'{name}.log'
    try:
        content = log_path.read_text(encoding='utf-8', errors='replace').lower()
    except FileNotFoundError:
        content = ''
    if rc != 0:
        if name == 'frontend-deps' and any(token in content for token in ('dns unavailable', 'temporary failure in name resolution', 'eai_again', 'frontend dependency bootstrap blocked')):
            return 'blocked'
        return 'failed'
    if name == 'frontend-build':
        if 'buildprofile=release' not in content and 'buildprofile=production' not in content:
            return 'blocked'
    if name == 'frontend-e2e' and '[frontend:e2e] skipped:' in content:
        return 'skipped'
    return 'passed'


def _derive_overall_status(step_statuses: dict[str, str], required_steps: list[str]) -> str:
    statuses = [str(step_statuses.get(name, 'not_executed') or 'not_executed') for name in required_steps]
    if any(status == 'failed' for status in statuses):
        return 'failed'
    if any(status in {'blocked', 'skipped'} for status in statuses):
        return 'blocked'
    if statuses and all(status == 'passed' for status in statuses):
        return 'passed'
    if any(status == 'passed' for status in statuses):
        return 'partial'
    return 'not_executed'


def write_verification_summary(*, artifact_dir: Path, step_statuses: dict[str, str], overall_status: str, required_steps: list[str]) -> None:
    import json
    summary_path = artifact_dir / 'verification_summary.json'
    payload = {
        'profile': PROFILE,
        'generatedAt': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'overallStatus': overall_status,
        'requiredSteps': required_steps,
        'stepStatuses': step_statuses,
        'logs': {name: f'{name}.log' for name in step_statuses},
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run frontend validation and emit auditable verification_summary.json.')
    parser.add_argument('--profile', default=PROFILE, choices=[PROFILE], help='artifact profile name')
    args = parser.parse_args(argv)
    artifact_dir = ROOT_DIR / 'artifacts' / 'repository_validation' / args.profile
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summary_path = artifact_dir / 'verification_summary.json'
    if summary_path.exists():
        summary_path.unlink()
    clean_hygiene_residue()
    steps = build_frontend_steps()
    required_steps = [name for name, *_ in steps]
    step_statuses: dict[str, str] = {}
    overall_status = 'running'
    for name, command, cwd, env in steps:
        rc = run_step(name, command, cwd=cwd, env=env, artifact_dir=artifact_dir)
        step_statuses[name] = _classify_frontend_step_status(name, rc, artifact_dir)
        if rc != 0:
            overall_status = _derive_overall_status(step_statuses, required_steps)
            write_verification_summary(artifact_dir=artifact_dir, step_statuses=step_statuses, overall_status=overall_status, required_steps=required_steps)
            return rc
        overall_status = _derive_overall_status(step_statuses, required_steps) if len(step_statuses) == len(required_steps) else 'running'
        write_verification_summary(artifact_dir=artifact_dir, step_statuses=step_statuses, overall_status=overall_status, required_steps=required_steps)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
