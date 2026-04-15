#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_runtime_baseline_report import build_report

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'config' / 'runtime_baseline_gate.yaml'
DEFAULT_OUT = ROOT / 'artifacts' / 'release_gates' / 'runtime_baseline_report.json'


def _load_thresholds(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(payload, dict):
        raise RuntimeError(f'invalid runtime baseline gate config: {path}')
    thresholds = payload.get('thresholds', {}) if isinstance(payload.get('thresholds'), dict) else {}
    return dict(thresholds)


def evaluate_report(report: dict[str, Any], *, thresholds: dict[str, Any]) -> dict[str, Any]:
    finished = int(report.get('counts', {}).get('taskRunFinished', 0) or 0)
    failed_runs = int(report.get('taskRunStatus', {}).get('failed', 0) or 0)
    action_bound = int(report.get('voiceTelemetry', {}).get('actionBoundEvents', 0) or 0)
    tiers = {str(key) for key, value in dict(report.get('runtimeTiers', {}) or {}).items() if int(value or 0) > 0}
    required_tiers = {str(item) for item in list(thresholds.get('require_runtime_tiers', []) or []) if str(item).strip()}
    checks = {
        'taskRunFinished': finished >= int(thresholds.get('min_task_run_finished', 1) or 0),
        'failedTaskRuns': failed_runs <= int(thresholds.get('max_failed_task_runs', 0) or 0),
        'voiceActionBoundEvents': action_bound <= int(thresholds.get('max_action_bound_voice_events', 0) or 0),
        'requiredRuntimeTiers': required_tiers.issubset(tiers) if required_tiers else True,
    }
    missing = [name for name, ok in checks.items() if not ok]
    return {
        'status': 'passed' if not missing else 'blocked',
        'checks': checks,
        'missingChecks': missing,
        'thresholds': thresholds,
        'report': report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Evaluate the runtime baseline report against release-gate thresholds.')
    parser.add_argument('--root', type=Path, required=True, help='gateway observability directory')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG, help='baseline threshold config path')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT, help='output JSON report path')
    args = parser.parse_args()

    thresholds = _load_thresholds(Path(args.config))
    report = build_report(Path(args.root))
    evaluation = evaluate_report(report, thresholds=thresholds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(args.out)
    return 0 if evaluation['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
