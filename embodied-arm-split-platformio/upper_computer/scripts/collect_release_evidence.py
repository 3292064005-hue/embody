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


def collect() -> dict[str, Any]:
    evidence_paths = [
        ROOT / 'artifacts' / 'target_env_report.json',
        ROOT / 'artifacts' / 'release_gates' / 'target_runtime_gate.json',
        ROOT / 'artifacts' / 'repository_validation',
        ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json',
        ROOT / 'docs' / 'generated' / 'runtime_contract_summary.md',
        ROOT / 'docs' / 'HIL_CHECKLIST.md',
    ]
    return {
        'generatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'evidence': [_path_record(path) for path in evidence_paths],
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
