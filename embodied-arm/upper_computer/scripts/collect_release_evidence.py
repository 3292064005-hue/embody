from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _path_record(path: Path) -> dict[str, Any]:
    return {
        'path': str(path.relative_to(ROOT)) if path.is_absolute() else str(path),
        'exists': path.exists(),
        'size': path.stat().st_size if path.exists() and path.is_file() else None,
    }


def _gate_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            'repoGate': 'not_executed',
            'targetGate': 'not_executed',
            'hilGate': 'not_executed',
            'releaseChecklistGate': 'not_executed',
            'releaseGate': 'not_executed',
        }
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {
            'repoGate': 'not_executed',
            'targetGate': 'not_executed',
            'hilGate': 'not_executed',
            'releaseChecklistGate': 'not_executed',
            'releaseGate': 'not_executed',
        }
    if not isinstance(payload, dict):
        return {
            'repoGate': 'not_executed',
            'targetGate': 'not_executed',
            'hilGate': 'not_executed',
            'releaseChecklistGate': 'not_executed',
            'releaseGate': 'not_executed',
        }
    return {
        'repoGate': payload.get('repoGate', 'not_executed'),
        'targetGate': payload.get('targetGate', 'not_executed'),
        'hilGate': payload.get('hilGate', 'not_executed'),
        'releaseChecklistGate': payload.get('releaseChecklistGate', 'not_executed'),
        'releaseGate': payload.get('releaseGate', 'not_executed'),
    }


def collect() -> dict[str, Any]:
    gate_report = ROOT / 'artifacts' / 'release_gates' / 'target_runtime_gate.json'
    evidence_paths = [
        ROOT / 'artifacts' / 'target_env_report.json',
        gate_report,
        ROOT / 'artifacts' / 'repository_validation',
        ROOT / 'artifacts' / 'repository_validation' / 'repo' / 'verification_summary.json',
        ROOT / 'artifacts' / 'release_gates' / 'runtime_baseline_report.json',
        ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json',
        ROOT / 'docs' / 'generated' / 'runtime_contract_summary.md',
        ROOT / 'docs' / 'HIL_CHECKLIST.md',
    ]
    return {
        'generatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'evidence': [_path_record(path) for path in evidence_paths],
        'gateSummary': _gate_summary(gate_report),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Collect release evidence artifacts into a single JSON manifest.')
    parser.add_argument('--out', default=str(ROOT / 'artifacts' / 'release_gates' / 'release_evidence.json'))
    args = parser.parse_args()
    report = collect()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
