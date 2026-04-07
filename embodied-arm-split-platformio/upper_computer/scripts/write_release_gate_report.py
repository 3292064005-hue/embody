from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VALID_STATUSES = {'passed', 'failed', 'blocked', 'skipped', 'not_executed'}


def _derive_target_runtime_readiness(steps: dict[str, str]) -> str:
    blocking = {value for key, value in steps.items() if key in {'env', 'ros_build', 'ros_smoke'} and value in {'failed', 'blocked'}}
    if blocking:
        return 'blocked'
    negative = steps.get('negative_path_subset', 'blocked')
    if negative == 'passed' and steps.get('hil') == 'passed':
        return 'passed'
    if negative in {'failed', 'blocked'} or steps.get('hil') in {'failed', 'blocked'}:
        return 'blocked'
    return 'skipped'


def build_gate_report(env_report: dict[str, Any], steps: dict[str, str], *, evidence_path: str | None = None) -> dict[str, Any]:
    blocking_steps = {name: value for name, value in steps.items() if value in {'failed', 'blocked'}}
    repo_gate = steps.get('repo_gate', 'not_executed')
    target_gate = steps.get('target_gate', _derive_target_runtime_readiness(steps))
    hil_gate = steps.get('hil', 'not_executed')
    return {
        'environment': env_report,
        'steps': steps,
        'allPassed': bool(steps) and all(value == 'passed' for value in steps.values()),
        'hasBlockingStep': bool(blocking_steps),
        'blockingSteps': blocking_steps,
        'negativePathCoverage': {
            'automaticSubset': steps.get('negative_path_subset', 'blocked'),
            'hil': hil_gate,
        },
        'repoGate': repo_gate,
        'targetGate': target_gate,
        'hilGate': hil_gate,
        'targetRuntimeReadiness': target_gate,
        'evidencePath': evidence_path,
    }


def write_report(report: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-report', default='artifacts/target_env_report.json')
    parser.add_argument('--out', default='artifacts/release_gates/target_runtime_gate.json')
    parser.add_argument('--step', action='append', default=[])
    parser.add_argument('--evidence-path', default='artifacts/release_gates/release_evidence.json')
    args = parser.parse_args()

    env_path = Path(args.env_report)
    env_report = json.loads(env_path.read_text(encoding='utf-8')) if env_path.exists() else {}
    steps: dict[str, str] = {}
    for item in args.step:
        name, _, status = item.partition('=')
        if not name or status not in VALID_STATUSES:
            raise SystemExit(f'invalid --step: {item}')
        steps[name] = status
    report = build_gate_report(env_report, steps, evidence_path=args.evidence_path)
    write_report(report, Path(args.out))
    print(Path(args.out))


if __name__ == '__main__':
    main()
