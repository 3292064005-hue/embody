#!/usr/bin/env python3
"""Deterministic repository verification orchestrator.

This replaces shell-function based orchestration with explicit subprocess
execution so each step has isolated logs and stable exit handling.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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


def npm_command() -> str:
    """Return an npm executable name that works with shell=False on each OS."""
    if os.name == 'nt':
        return shutil.which('npm.cmd') or shutil.which('npm') or 'npm.cmd'
    return shutil.which('npm') or 'npm'


def repo_python_env() -> dict[str, str]:
    """Keep repository Python runs isolated from host ROS Python overlays.

    ROS 2 Humble commonly injects Python 3.10 site-packages into PYTHONPATH.
    Repository verification may run under a different interpreter, and those
    host paths can make pytest autoload ROS plugins or import ROS packages
    before the repo-local modules. Putting the repo root first also keeps
    ``import scripts.*`` bound to this repository instead of ROS packages.
    Target-runtime checks source ROS explicitly; this repo lane should stay
    interpreter-local.
    """
    env = {'PYTHONDONTWRITEBYTECODE': '1'}
    filtered = [str(ROOT_DIR)]
    pythonpath = os.environ.get('PYTHONPATH')
    if pythonpath:
        filtered.extend(
            entry for entry in pythonpath.split(os.pathsep)
            if entry and '/opt/ros/' not in entry
        )
    env['PYTHONPATH'] = os.pathsep.join(filtered)
    return env


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
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd or ROOT_DIR),
                env=merged_env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            log_file.write(f'failed to start command: {list(command)!r}\n{exc}\n')
            completed_rc = 127
            process = None
        while True:
            if process is None:
                break
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


def _classify_step_status(name: str, rc: int, artifact_dir: Path) -> str:
    """Map one verification step to an auditable status token.

    `frontend-e2e` may exit zero when the environment intentionally fail-closes
    to a skip (for example, no usable Chromium). That semantic skip must not be
    recorded as `passed`, otherwise downstream ledgers and release evidence
    would overstate verification coverage.
    """
    if rc != 0:
        return 'failed'
    if name == 'frontend-deps':
        log_path = artifact_dir / f'{name}.log'
        try:
            content = log_path.read_text(encoding='utf-8', errors='replace').lower()
        except FileNotFoundError:
            content = ''
        if any(token in content for token in ('dns unavailable', 'temporary failure in name resolution', 'eai_again', 'frontend dependency bootstrap blocked')):
            return 'blocked'
    if name == 'frontend-e2e':
        log_path = artifact_dir / f'{name}.log'
        try:
            content = log_path.read_text(encoding='utf-8', errors='replace').lower()
        except FileNotFoundError:
            content = ''
        if '[frontend:e2e] skipped:' in content:
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


def build_steps(profile: str) -> list[tuple[str, Sequence[str], Path | None, dict[str, str] | None]]:
    python = sys.executable
    npm = npm_command()
    steps: list[tuple[str, Sequence[str], Path | None, dict[str, str] | None]] = []
    python_env = repo_python_env()
    if profile in {'repo', 'release'}:
        steps.append(('backend-full', [python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'], BACKEND_DIR, python_env))
    frontend_release_env = {
        'EMBODIED_ARM_BUILD_PROFILE': 'release',
        'PLAYWRIGHT_CHROMIUM_EXECUTABLE': os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE', ''),
    }
    steps.extend([
        ('backend-active', [python, '-m', 'pytest', '-q', '-c', 'pytest-active.ini', '-p', 'no:cacheprovider'], BACKEND_DIR, python_env),
        ('active-profile-consistency', [python, str(ROOT_DIR / 'scripts' / 'check_active_profile_consistency.py')], ROOT_DIR, python_env),
        ('deprecated-runtime-usage', [python, str(ROOT_DIR / 'scripts' / 'check_deprecated_runtime_usage.py')], ROOT_DIR, python_env),
        ('interface-mirror-drift', [python, str(ROOT_DIR / 'scripts' / 'sync_interface_mirror.py'), '--check'], ROOT_DIR, python_env),
        ('contract-artifacts', [python, str(ROOT_DIR / 'scripts' / 'generate_contract_artifacts.py'), '--check'], ROOT_DIR, python_env),
        ('runtime-contracts', [python, str(ROOT_DIR / 'scripts' / 'validate_runtime_contracts.py')], ROOT_DIR, python_env),
        ('runtime-baseline-report', [python, str(ROOT_DIR / 'scripts' / 'check_runtime_baseline_gate.py'), '--root', str(ROOT_DIR / 'gateway' / 'tests' / 'fixtures' / 'observability_sample'), '--out', str(ROOT_DIR / 'artifacts' / 'release_gates' / 'runtime_baseline_report.json')], ROOT_DIR, python_env),
        ('gateway', [python, '-m', 'pytest', '-q', 'gateway/tests', '-p', 'no:cacheprovider'], ROOT_DIR, python_env),
        ('frontend-deps', ['bash', 'scripts/ensure_frontend_deps.sh'], ROOT_DIR, None),
        ('frontend-typecheck-app', [npm, 'run', 'typecheck'], FRONTEND_DIR, frontend_release_env),
        ('frontend-typecheck-test', [npm, 'run', 'typecheck:test'], FRONTEND_DIR, frontend_release_env),
        ('frontend-unit', [npm, 'run', 'test:unit'], FRONTEND_DIR, frontend_release_env),
        ('frontend-build', [npm, 'run', 'build'], FRONTEND_DIR, frontend_release_env),
        ('frontend-e2e', ['node', './scripts/run-playwright-e2e.mjs'], FRONTEND_DIR, {**frontend_release_env, 'FRONTEND_E2E_STRICT': '0'}),
        ('frontend-validation-evidence', [python, str(ROOT_DIR / 'scripts' / 'write_frontend_validation_status.py')], ROOT_DIR, python_env),
        ('doc-compatibility-refresh', [python, str(ROOT_DIR / 'scripts' / 'sync_doc_compatibility_mirrors.py')], ROOT_DIR, python_env),
        ('doc-compatibility-mirrors', [python, str(ROOT_DIR / 'scripts' / 'sync_doc_compatibility_mirrors.py'), '--check'], ROOT_DIR, python_env),
        ('release-support-artifacts', [python, str(ROOT_DIR / 'scripts' / 'materialize_release_support_artifacts.py')], ROOT_DIR, python_env),
        ('release-evidence', [python, str(ROOT_DIR / 'scripts' / 'collect_release_evidence.py')], ROOT_DIR, python_env),
        ('release-manifest', [python, str(ROOT_DIR / 'scripts' / 'package_release.py')], ROOT_DIR, python_env),
        ('split-release-manifest', [python, str(ROOT_DIR.parent / 'scripts' / 'package_split_release.py')], ROOT_DIR.parent, python_env),
        ('audit', [python, str(ROOT_DIR / 'scripts' / 'final_audit.py')], ROOT_DIR, python_env),
    ])
    if profile == 'release':
        steps.extend([
            ('release-contract-artifacts', [python, str(ROOT_DIR / 'scripts' / 'generate_contract_artifacts.py'), '--check'], ROOT_DIR, python_env),
            ('release-package', [python, str(ROOT_DIR.parent / 'scripts' / 'package_split_release.py'), '--check'], ROOT_DIR.parent, python_env),
        ])
    return steps


def _write_verification_summary(*, profile: str, artifact_dir: Path, step_statuses: dict[str, str], overall_status: str, required_steps: list[str]) -> None:
    summary_path = artifact_dir / 'verification_summary.json'
    payload = {
        'profile': profile,
        'generatedAt': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'generatedBy': 'scripts/verify_repository.py',
        'overallStatus': overall_status,
        'requiredSteps': required_steps,
        'stepStatuses': step_statuses,
        'logs': {name: f'{name}.log' for name in step_statuses},
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='repo', choices=['fast', 'repo', 'release'])
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
    overall_status = 'running'
    for name, command, cwd, env in steps:
        rc = run_step(name, command, cwd=cwd, env=env, artifact_dir=artifact_dir)
        step_statuses[name] = _classify_step_status(name, rc, artifact_dir)
        if rc != 0:
            overall_status = _derive_overall_status(step_statuses, required_steps)
            _write_verification_summary(profile=args.profile, artifact_dir=artifact_dir, step_statuses=step_statuses, overall_status=overall_status, required_steps=required_steps)
            return rc
        overall_status = _derive_overall_status(step_statuses, required_steps) if len(step_statuses) == len(required_steps) else 'running'
        _write_verification_summary(profile=args.profile, artifact_dir=artifact_dir, step_statuses=step_statuses, overall_status=overall_status, required_steps=required_steps)
        if name == 'frontend-e2e':
            clean_hygiene_residue()
    _write_verification_summary(profile=args.profile, artifact_dir=artifact_dir, step_statuses=step_statuses, overall_status=overall_status, required_steps=required_steps)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
