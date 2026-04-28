from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_authority import build_validated_live_governance_ledger
from scripts.release_state_model import build_release_gate_report


def _resolve_repo_path(path: Path) -> Path:
    """Resolve a release-evidence path under the upper-computer repository root.

    Args:
        path: Absolute path or path relative to `ROOT`.

    Returns:
        Absolute path normalized without requiring the file to exist.

    Raises:
        ValueError: If the path resolves outside `ROOT`. Release evidence uses
        repository-relative paths as its stable schema, so external output paths
        are rejected instead of being represented ambiguously.

    Boundary behavior:
        Missing in-repository paths are accepted so clean first-run ledgers can
        represent absent evidence artifacts explicitly.
    """
    absolute = path if path.is_absolute() else ROOT / path
    resolved = absolute.resolve(strict=False)
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f'release evidence path must be inside upper_computer root: {resolved}') from exc
    return resolved


def _repo_relative(path: Path) -> str:
    """Render a normalized repository-relative evidence path.

    Args:
        path: Absolute or repository-relative path that must resolve inside
            `ROOT`.

    Returns:
        POSIX repository-relative path suitable for JSON ledgers.

    Raises:
        ValueError: If `path` resolves outside `ROOT`.

    Boundary behavior:
        The returned path is POSIX-stable even on non-POSIX hosts.
    """
    return _resolve_repo_path(path).relative_to(ROOT).as_posix()


def _path_record(path: Path, *, output_path: Path | None = None) -> dict[str, Any]:
    """Build a stable release-evidence file record.

    Args:
        path: Evidence artifact path, absolute or repository-relative.
        output_path: Optional path of the evidence JSON currently being written.

    Returns:
        A JSON-safe record with compatibility fields (`exists`, `size`) plus
        provenance fields (`sizeBytes`, `sha256`, `provenanceStatus`).

    Raises:
        ValueError: If `path` or `output_path` resolves outside `ROOT`. Missing
        evidence files inside `ROOT` are represented explicitly and do not raise.

    Boundary behavior:
        The release evidence JSON cannot embed a final SHA-256 of itself because
        writing that digest would change the file bytes. When `path` equals
        `output_path`, the record is marked `self_referential_output`, reports
        post-write `exists=True`, and intentionally leaves size and digest fields
        as `None`.
    """
    absolute = _resolve_repo_path(path)
    relative = absolute.relative_to(ROOT).as_posix()
    normalized_output = _resolve_repo_path(output_path) if output_path is not None else None
    is_self_reference = normalized_output is not None and absolute == normalized_output
    exists = absolute.exists()
    is_file = absolute.is_file()
    size = absolute.stat().st_size if exists and is_file else None
    if is_self_reference:
        exists = True
        is_file = True
        size = None
    record: dict[str, Any] = {
        'path': relative,
        'exists': exists,
        'size': size,
        'sizeBytes': size,
        'sha256': None,
        'provenanceStatus': 'missing',
    }
    if is_self_reference:
        record['selfReference'] = True
        record['size'] = None
        record['sizeBytes'] = None
        record['provenanceStatus'] = 'self_referential_output'
        return record
    if not exists:
        return record
    if not is_file:
        record['provenanceStatus'] = 'not_a_file'
        return record
    record['sha256'] = hashlib.sha256(absolute.read_bytes()).hexdigest()
    record['provenanceStatus'] = 'recorded'
    return record


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _canonical_release_steps(*, gate_report: Path, env_report: Path, runtime_baseline_report: Path) -> tuple[dict[str, Any], dict[str, str]]:
    gate_payload = _load_json(gate_report)
    steps = gate_payload.get('steps', {}) if isinstance(gate_payload.get('steps'), dict) else {}
    normalized_steps = {str(name): str(value or 'not_executed') for name, value in dict(steps).items()}
    env_payload = _load_json(env_report)
    if 'env' not in normalized_steps:
        normalized_steps['env'] = 'passed' if bool(env_payload.get('ok', False)) else ('blocked' if env_payload else 'not_executed')
    baseline_payload = _load_json(runtime_baseline_report)
    if 'runtime_baseline' not in normalized_steps:
        normalized_steps['runtime_baseline'] = str(baseline_payload.get('status', 'not_executed') or 'not_executed')
    normalized_steps.setdefault('ros_build', 'not_executed')
    normalized_steps.setdefault('ros_smoke', 'not_executed')
    normalized_steps.setdefault('negative_path_subset', 'not_executed')
    normalized_steps.setdefault('hil', 'not_executed')
    normalized_steps.setdefault('release_checklist', 'not_executed')
    return env_payload, normalized_steps


def _gate_summary(path: Path) -> dict[str, Any]:
    env_payload, steps = _canonical_release_steps(
        gate_report=path,
        env_report=ROOT / 'artifacts' / 'target_env_report.json',
        runtime_baseline_report=ROOT / 'artifacts' / 'release_gates' / 'runtime_baseline_report.json',
    )
    payload = build_release_gate_report(env_payload, steps, root=ROOT, evidence_path=str(ROOT / 'artifacts' / 'release_gates' / 'release_evidence.json'))
    return {
        'repoGate': payload.get('repoGate', 'not_executed'),
        'targetGate': payload.get('targetGate', 'not_executed'),
        'hilGate': payload.get('hilGate', 'not_executed'),
        'releaseChecklistGate': payload.get('releaseChecklistGate', 'not_executed'),
        'releaseGate': payload.get('releaseGate', 'not_executed'),
    }


def _frontend_validation_summary(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    matrix = payload.get('matrix', []) if isinstance(payload.get('matrix'), list) else []
    return {
        'overallStatus': str(payload.get('overallStatus', 'not_executed') or 'not_executed'),
        'sourceProfile': str(payload.get('sourceProfile', '') or ''),
        'sourceSummary': str(payload.get('sourceSummary', '') or ''),
        'stepCount': len(matrix),
        'passedSteps': sum(1 for item in matrix if isinstance(item, dict) and str(item.get('status', '') or '') == 'passed'),
        'failedSteps': sum(1 for item in matrix if isinstance(item, dict) and str(item.get('status', '') or '') == 'failed'),
        'blockedSteps': sum(1 for item in matrix if isinstance(item, dict) and str(item.get('status', '') or '') == 'blocked'),
        'skippedSteps': sum(1 for item in matrix if isinstance(item, dict) and str(item.get('status', '') or '') == 'skipped'),
        'notExecutedSteps': sum(1 for item in matrix if isinstance(item, dict) and str(item.get('status', 'not_executed') or 'not_executed') == 'not_executed'),
        'ledgerPath': str(path.relative_to(ROOT)),
    }


def _doc_compatibility_summary(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    entries = payload.get('entries', []) if isinstance(payload.get('entries'), list) else []
    return {
        'entryCount': len(entries),
        'generatedBy': str(payload.get('generatedBy', '') or ''),
        'manifestPath': str(path.relative_to(ROOT)),
        'entries': [dict(item) for item in entries if isinstance(item, dict)],
    }


def collect(output_path: Path | None = None) -> dict[str, Any]:
    """Collect release gate evidence and file-level provenance.

    Args:
        output_path: Optional destination for the evidence JSON. When supplied,
        a matching evidence path is treated as a self-reference and is not
        assigned an impossible final SHA-256.

    Returns:
        A JSON-safe evidence ledger containing gate summaries, validation
        summaries, compatibility mirror state and per-file provenance.

    Raises:
        No exception is raised for absent evidence artifacts. Missing files are
        represented as explicit records so the release gate can fail closed in
        audit code. ValueError is raised when the requested output path is
        outside `ROOT`, because the ledger schema is repository-relative.

    Boundary behavior:
        The generated ledger records normal evidence files with SHA-256 and byte
        size. Its own output path, if included, is marked as
        `self_referential_output` because the final digest cannot be known before
        the file is written.
    """
    gate_report = ROOT / 'artifacts' / 'release_gates' / 'target_runtime_gate.json'
    frontend_ledger = ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_ledger.json'
    doc_manifest = ROOT / 'docs' / 'generated' / 'doc_compatibility_manifest.json'
    release_evidence = _resolve_repo_path(output_path or ROOT / 'artifacts' / 'release_gates' / 'release_evidence.json')
    evidence_paths = [
        release_evidence,
        ROOT / 'artifacts' / 'target_env_report.json',
        ROOT / 'artifacts' / 'release_gates' / 'validated_live_hil_gate.json',
        ROOT / 'artifacts' / 'release_gates' / 'validated_live_release_checklist_gate.json',
        gate_report,
        ROOT / 'artifacts' / 'repository_validation' / 'repo' / 'verification_summary.json',
        ROOT / 'artifacts' / 'release_gates' / 'runtime_baseline_report.json',
        ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_artifacts' / 'verification_summary.json',
        ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_artifacts' / 'frontend-deps.log',
        ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_artifacts' / 'frontend-typecheck-app.log',
        ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_artifacts' / 'frontend-typecheck-test.log',
        ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_artifacts' / 'frontend-unit.log',
        ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_artifacts' / 'frontend-build.log',
        ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_artifacts' / 'frontend-e2e.log',
        frontend_ledger,
        ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json',
        ROOT / 'docs' / 'generated' / 'runtime_contract_summary.md',
        doc_manifest,
        ROOT / 'docs' / 'evidence' / 'frontend-validation-status.md',
        ROOT / 'docs' / 'evidence' / 'validated_live' / 'target_runtime_gate.md',
        ROOT / 'docs' / 'evidence' / 'validated_live' / 'hil_smoke_report.md',
        ROOT / 'docs' / 'evidence' / 'validated_live' / 'release_checklist.md',
    ]
    return {
        'generatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'evidence': [_path_record(path, output_path=release_evidence) for path in evidence_paths],
        'gateSummary': _gate_summary(gate_report),
        'frontendValidation': _frontend_validation_summary(frontend_ledger),
        'docCompatibilityMirrors': _doc_compatibility_summary(doc_manifest),
        'validatedLiveGovernance': build_validated_live_governance_ledger(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Collect release evidence artifacts into a single JSON manifest.')
    parser.add_argument('--out', default=str(ROOT / 'artifacts' / 'release_gates' / 'release_evidence.json'))
    args = parser.parse_args()
    out_path = Path(args.out)
    try:
        report = collect(out_path)
    except ValueError as exc:
        parser.error(str(exc))
    out_path = _resolve_repo_path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
