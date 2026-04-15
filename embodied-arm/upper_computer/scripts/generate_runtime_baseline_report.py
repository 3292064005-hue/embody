from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DEFAULT_ROOT = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state')) / 'embodied-arm' / 'gateway_observability'


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _numeric_values(records: Iterable[dict[str, Any]], field: str) -> list[float]:
    values: list[float] = []
    for item in records:
        try:
            value = float(item.get(field, 0.0) or 0.0)
        except Exception:
            continue
        if value > 0.0:
            values.append(value)
    return values


def _summary_stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {'count': 0, 'min': None, 'max': None, 'avg': None}
    return {
        'count': len(values),
        'min': round(min(values), 3),
        'max': round(max(values), 3),
        'avg': round(sum(values) / len(values), 3),
    }


def build_report(root: Path) -> dict[str, Any]:
    logs = _read_jsonl(root / 'logs.jsonl')
    audits = _read_jsonl(root / 'audits.jsonl')
    task_runs = _read_jsonl(root / 'task_runs.jsonl')

    finished_runs = [item for item in task_runs if str(item.get('event', '')) == 'task_run.finished']
    progress_events = [item for item in task_runs if str(item.get('event', '')) == 'task_run.progress']
    voice_events = [item for item in logs if str(item.get('event', '')).startswith('voice.event.')]

    log_levels = Counter(str(item.get('level', 'info') or 'info') for item in logs)
    audit_actions = Counter(str(item.get('action', 'unknown') or 'unknown') for item in audits)
    task_run_status = Counter('success' if bool(item.get('success', False)) else 'failed' for item in finished_runs)
    runtime_tiers = Counter(str(item.get('runtimeTier', 'unknown') or 'unknown') for item in finished_runs)

    report = {
        'observabilityRoot': str(root),
        'files': {
            'logs': str(root / 'logs.jsonl'),
            'audits': str(root / 'audits.jsonl'),
            'task_runs': str(root / 'task_runs.jsonl'),
        },
        'counts': {
            'logs': len(logs),
            'audits': len(audits),
            'taskRunEvents': len(task_runs),
            'taskRunFinished': len(finished_runs),
            'taskRunProgress': len(progress_events),
            'voiceTelemetryEvents': len(voice_events),
        },
        'logLevels': _counter_payload(log_levels),
        'auditActions': _counter_payload(audit_actions),
        'taskRunStatus': _counter_payload(task_run_status),
        'runtimeTiers': _counter_payload(runtime_tiers),
        'durationsMs': _summary_stats(_numeric_values(finished_runs, 'durationMs')),
        'voiceTelemetry': {
            'telemetryOnlyEvents': sum(1 for item in voice_events if bool(item.get('payload', {}).get('telemetryOnly', False))),
            'actionBoundEvents': sum(1 for item in voice_events if bool(item.get('payload', {}).get('actionExecutionBound', False))),
        },
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate a runtime baseline report from gateway observability JSONL streams.')
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT, help='gateway observability directory')
    parser.add_argument('--output', type=Path, default=None, help='optional output JSON file path')
    args = parser.parse_args()

    report = build_report(Path(args.root))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(payload + '\n', encoding='utf-8')
    print(payload)


if __name__ == '__main__':
    main()
