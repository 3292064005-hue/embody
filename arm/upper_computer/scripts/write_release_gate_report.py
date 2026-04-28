from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_state_model import VALID_STATUSES, build_release_gate_report


def build_gate_report(
    env_report: dict[str, Any],
    steps: dict[str, str],
    *,
    evidence_path: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the shared release-state model.

    Args:
        env_report: Parsed environment report payload.
        steps: Raw release-step statuses.
        evidence_path: Optional path to the collected release-evidence manifest.
        root: Optional repository root override used by tests.

    Returns:
        Canonical release-gate report.

    Raises:
        Does not raise. Invalid statuses are normalized by the shared state model.
    """
    return build_release_gate_report(env_report, steps, root=root or ROOT, evidence_path=evidence_path)


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
    report = build_gate_report(env_report, steps, evidence_path=args.evidence_path, root=ROOT)
    write_report(report, Path(args.out))
    print(Path(args.out))


if __name__ == '__main__':
    main()
