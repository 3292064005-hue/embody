#!/usr/bin/env python3
"""Deterministic repository verification orchestrator.

This replaces shell-function based orchestration with explicit subprocess
execution so each step has isolated logs and stable exit handling.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / 'backend' / 'embodied_arm_ws'
FRONTEND_DIR = ROOT_DIR / 'frontend'


def clean_hygiene_residue() -> None:
    for pattern in ('__pycache__', '.pytest_cache'):
        for path in ROOT_DIR.rglob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
    for suffix in ('*.pyc', '*.tsbuildinfo'):
        for path in ROOT_DIR.rglob(suffix):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def run_step(name: str, command: Sequence[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
             artifact_dir: Path) -> int:
    """Run one verification step with deterministic logging and quiet-step heartbeats.

    Args:
        name: Stable step identifier used in stdout and artifact log naming.
        command: Subprocess argv executed without shell interpolation.
        cwd: Optional working directory; defaults to repository root.
        env: Optional environment overrides merged onto the current process env.
        artifact_dir: Directory that stores step logs.

    Returns:
        int: Process return code. Zero means the step completed successfully.

    Boundary behavior:
        - Stdout/stderr of the child process are always redirected into the step log.
        - For long quiet steps such as typecheck/build, this function emits a heartbeat
          every 3 seconds so CI/sandbox runners do not misclassify the step as hung.
        - On failure, the tail of the log is mirrored to stderr for immediate diagnosis.
    """
    log_path = artifact_dir / f'{name}.log'
    print(f'[verify] {name}', flush=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    start = time.monotonic()
    heartbeat_interval = 3.0
    next_heartbeat = start + heartbeat_interval
    with log_path.open('w', encoding='utf-8') as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(cwd or ROOT_DIR),
            env=merged_env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        while True:
            returncode = process.poll()
            now = time.monotonic()
            if returncode is not None:
                completed_rc = int(returncode)
                break
            if now >= next_heartbeat:
                elapsed = int(now - start)
                print(f'[verify] {name}: running ({elapsed}s elapsed, log={log_path})', flush=True)
                next_heartbeat = now + heartbeat_interval
            time.sleep(0.25)
    if completed_rc == 0:
        print(f'[verify] {name}: passed', flush=True)
        return 0
    print(f'[verify] {name}: failed (see {log_path})', file=sys.stderr, flush=True)
    try:
        lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
    except FileNotFoundError:
        lines = []
    for line in lines[-200:]:
        print(line, file=sys.stderr)
    return completed_rc


def build_steps(profile: str) -> list[tuple[str, Sequence[str], Path | None, dict[str, str] | None]]:
    python = sys.executable
    steps: list[tuple[str, Sequence[str], Path | None, dict[str, str] | None]] = []
    if profile == 'repo':
        steps.append(('backend-full', [python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'], BACKEND_DIR, {'PYTHONDONTWRITEBYTECODE': '1'}))
    steps.extend([
        ('backend-active', [python, '-m', 'pytest', '-q', '-c', 'pytest-active.ini', '-p', 'no:cacheprovider'], BACKEND_DIR, {'PYTHONDONTWRITEBYTECODE': '1'}),
        ('active-profile-consistency', [python, str(ROOT_DIR / 'scripts' / 'check_active_profile_consistency.py')], ROOT_DIR, None),
        ('interface-mirror-drift', [python, str(ROOT_DIR / 'scripts' / 'sync_interface_mirror.py'), '--check'], ROOT_DIR, None),
        ('contract-artifacts', [python, str(ROOT_DIR / 'scripts' / 'generate_contract_artifacts.py'), '--check'], ROOT_DIR, None),
        ('runtime-contracts', [python, str(ROOT_DIR / 'scripts' / 'validate_runtime_contracts.py')], ROOT_DIR, None),
        ('gateway', [python, '-m', 'pytest', '-q', 'gateway/tests', '-p', 'no:cacheprovider'], ROOT_DIR, {'PYTHONDONTWRITEBYTECODE': '1'}),
        ('frontend-deps', ['bash', 'scripts/ensure_frontend_deps.sh'], ROOT_DIR, None),
        ('frontend-typecheck-app', ['npm', 'run', 'typecheck'], FRONTEND_DIR, None),
        ('frontend-typecheck-test', ['npm', 'run', 'typecheck:test'], FRONTEND_DIR, None),
        ('frontend-unit', ['npm', 'run', 'test:unit'], FRONTEND_DIR, None),
        ('frontend-build', ['npm', 'run', 'build'], FRONTEND_DIR, None),
        ('frontend-e2e', ['node', './scripts/run-playwright-e2e.mjs'], FRONTEND_DIR, None),
        ('audit', [python, str(ROOT_DIR / 'scripts' / 'final_audit.py')], ROOT_DIR, None),
    ])
    return steps


def _write_verification_summary(*, profile: str, artifact_dir: Path, step_statuses: dict[str, str], overall_status: str, required_steps: list[str]) -> None:
    summary_path = artifact_dir / 'verification_summary.json'
    payload = {
        'profile': profile,
        'overallStatus': overall_status,
        'requiredSteps': required_steps,
        'stepStatuses': step_statuses,
        'logs': {name: f'{name}.log' for name in step_statuses},
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='repo', choices=['fast', 'repo'])
    args = parser.parse_args()

    artifact_dir = ROOT_DIR / 'artifacts' / 'repository_validation' / args.profile
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summary_path = artifact_dir / 'verification_summary.json'
    if summary_path.exists():
        summary_path.unlink()
    print(f'[verify] profile={args.profile}', flush=True)
    clean_hygiene_residue()
    steps = build_steps(args.profile)
    required_steps = [name for name, *_ in steps]
    step_statuses: dict[str, str] = {}
    overall_status = 'passed'
    for name, command, cwd, env in steps:
        rc = run_step(name, command, cwd=cwd, env=env, artifact_dir=artifact_dir)
        step_statuses[name] = 'passed' if rc == 0 else 'failed'
        if rc != 0:
            overall_status = 'failed'
            _write_verification_summary(profile=args.profile, artifact_dir=artifact_dir, step_statuses=step_statuses, overall_status=overall_status, required_steps=required_steps)
            return rc
        if name == 'frontend-e2e':
            clean_hygiene_residue()
    _write_verification_summary(profile=args.profile, artifact_dir=artifact_dir, step_statuses=step_statuses, overall_status=overall_status, required_steps=required_steps)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
