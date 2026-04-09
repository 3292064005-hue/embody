from __future__ import annotations

"""Shared release-gate state model used by reporting, validation, and promotion.

This module normalizes release-step statuses into layered gates so repository
validation, target-runtime validation, HIL evidence, and final release
readiness do not impersonate each other.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

VALID_STATUSES = {'passed', 'failed', 'blocked', 'skipped', 'not_executed'}


@dataclass(frozen=True)
class ReleaseGateState:
    """Normalized release-gate projection.

    Attributes:
        repo_gate: Repository-level verification result.
        target_gate: Target-runtime gate result derived from environment/build/smoke.
        hil_gate: HIL execution result.
        release_checklist_gate: Checklist sign-off result.
        release_gate: Final publishability verdict across all gates.
        blocking_steps: Individual step failures or blockers.
    """

    repo_gate: str
    target_gate: str
    hil_gate: str
    release_checklist_gate: str
    release_gate: str
    blocking_steps: dict[str, str]


def normalize_status(value: str | None) -> str:
    normalized = str(value or 'not_executed').strip()
    return normalized if normalized in VALID_STATUSES else 'not_executed'


def gate_from_required_steps(steps: dict[str, str], *, required: tuple[str, ...]) -> str:
    """Reduce a set of required steps into one gate status.

    Args:
        steps: Raw or normalized step-status mapping.
        required: Step names that must pass for the gate to pass.

    Returns:
        One normalized gate status.

    Raises:
        Does not raise.

    Boundary behavior:
        - Any failed step makes the gate fail.
        - Any blocked step makes the gate blocked.
        - Partial execution without full pass remains blocked rather than passed.
    """
    observed = [normalize_status(steps.get(name)) for name in required]
    if any(status == 'failed' for status in observed):
        return 'failed'
    if any(status == 'blocked' for status in observed):
        return 'blocked'
    if observed and all(status == 'passed' for status in observed):
        return 'passed'
    if any(status in {'passed', 'skipped'} for status in observed):
        return 'blocked'
    if any(status == 'skipped' for status in observed):
        return 'skipped'
    return 'not_executed'


def _derive_repo_gate(steps: dict[str, str], *, root: Path) -> str:
    """Derive the repository gate from machine-readable repository evidence.

    The canonical repo gate must come from a verification summary produced by
    ``scripts/verify_repository.py`` so stale or partial log files cannot be
    interpreted as a successful repository gate. Caller-supplied gate fields are
    ignored.
    """
    summary_path = root / 'artifacts' / 'repository_validation' / 'repo' / 'verification_summary.json'
    if not summary_path.exists():
        return 'not_executed'
    try:
        import json

        payload = json.loads(summary_path.read_text(encoding='utf-8'))
    except Exception:
        return 'not_executed'
    if not isinstance(payload, dict):
        return 'not_executed'
    if str(payload.get('profile', '') or '').strip() != 'repo':
        return 'not_executed'
    if normalize_status(str(payload.get('overallStatus', '') or '')) != 'passed':
        return 'failed' if normalize_status(str(payload.get('overallStatus', '') or '')) == 'failed' else 'not_executed'
    required_steps = payload.get('requiredSteps', []) if isinstance(payload.get('requiredSteps'), list) else []
    step_statuses = payload.get('stepStatuses', {}) if isinstance(payload.get('stepStatuses'), dict) else {}
    if not required_steps or not step_statuses:
        return 'not_executed'
    for step_name in required_steps:
        status = normalize_status(step_statuses.get(str(step_name)))
        if status != 'passed':
            return status if status in {'failed', 'blocked'} else 'not_executed'
    log_dir = summary_path.parent
    for step_name in required_steps:
        log_path = log_dir / f'{step_name}.log'
        if not log_path.exists():
            return 'not_executed'
    return 'passed'


def _validated_live_evidence_payload(root: Path) -> dict[str, Any]:
    evidence_path = root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'validated_live_evidence.yaml'
    if not evidence_path.exists():
        return {}
    try:
        payload = yaml.safe_load(evidence_path.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _derive_evidence_gate(*, root: Path, marker: str) -> str:
    """Derive one validated-live evidence gate from the canonical evidence manifest.

    Missing files, malformed payloads, missing artifacts, or unknown statuses all
    fail closed rather than passing.
    """
    payload = _validated_live_evidence_payload(root)
    evidence = payload.get('evidence', {}) if isinstance(payload.get('evidence'), dict) else {}
    item = evidence.get(marker, {}) if isinstance(evidence.get(marker), dict) else {}
    raw_status = str(item.get('status', '') or '').strip().lower()
    artifact = str(item.get('artifact', '') or '').strip()
    artifact_path = (root / artifact) if artifact else None
    if artifact_path is None or not artifact_path.exists():
        return 'not_executed'
    if raw_status == 'passed':
        return 'passed'
    if raw_status in {'failed', 'blocked'}:
        return raw_status
    if marker == 'release_checklist_signed' and raw_status == 'not_signed':
        return 'blocked'
    if raw_status == 'skipped':
        return 'blocked'
    return 'not_executed'


def _derive_hil_gate(*, root: Path) -> str:
    return _derive_evidence_gate(root=root, marker='hil_gate_passed')


def _derive_release_checklist_gate(steps: dict[str, str], *, root: Path) -> str:
    """Derive the release-checklist gate from validated-live evidence.

    The checklist gate is authoritative only when backed by the machine-readable
    validated-live evidence manifest. Caller-provided gate fields are ignored so
    they cannot drift from the evidence artifact.
    """
    return _derive_evidence_gate(root=root, marker='release_checklist_signed')


def derive_release_gate_state(steps: dict[str, str], *, root: Path) -> ReleaseGateState:
    """Derive layered release gates from raw step statuses.

    Args:
        steps: Raw step-status mapping.
        root: Repository root used to inspect repository-validation and checklist
            artifacts when explicit gate statuses are omitted.

    Returns:
        ReleaseGateState with separated repo/target/HIL/release-checklist verdicts.

    Raises:
        Does not raise. Unknown statuses degrade to ``not_executed``.
    """
    normalized = {str(name): normalize_status(value) for name, value in steps.items()}
    repo_gate = _derive_repo_gate(normalized, root=root)
    target_gate = gate_from_required_steps(normalized, required=('env', 'ros_build', 'ros_smoke', 'negative_path_subset'))
    hil_gate = _derive_hil_gate(root=root)
    release_checklist_gate = _derive_release_checklist_gate(normalized, root=root)

    blocking_steps = {name: status for name, status in normalized.items() if status in {'failed', 'blocked'}}

    if any(status == 'failed' for status in (repo_gate, target_gate, hil_gate, release_checklist_gate)):
        release_gate = 'failed'
    elif repo_gate == 'passed' and target_gate == 'passed' and hil_gate == 'passed' and release_checklist_gate == 'passed':
        release_gate = 'passed'
    elif any(status == 'blocked' for status in (repo_gate, target_gate, hil_gate, release_checklist_gate)):
        release_gate = 'blocked'
    elif any(status in {'passed', 'skipped'} for status in (repo_gate, target_gate, hil_gate, release_checklist_gate)):
        release_gate = 'blocked'
    else:
        release_gate = 'not_executed'

    return ReleaseGateState(
        repo_gate=repo_gate,
        target_gate=target_gate,
        hil_gate=hil_gate,
        release_checklist_gate=release_checklist_gate,
        release_gate=release_gate,
        blocking_steps=blocking_steps,
    )


def build_release_gate_report(env_report: dict[str, Any], steps: dict[str, str], *, root: Path, evidence_path: str | None = None) -> dict[str, Any]:
    """Build the canonical release-gate JSON report.

    Args:
        env_report: Parsed environment report payload.
        steps: Raw release-step statuses.
        root: Repository root used to derive missing gate inputs.
        evidence_path: Optional release-evidence manifest path.

    Returns:
        Serializable release-gate report. The ``steps`` section is rewritten to
        authoritative, normalized values so derived gates cannot contradict the
        raw inputs that produced them.

    Raises:
        Does not raise. Missing inputs fail closed.
    """
    normalized_steps = {str(name): normalize_status(value) for name, value in steps.items()}
    state = derive_release_gate_state(normalized_steps, root=root)
    authoritative_steps = dict(normalized_steps)
    authoritative_steps['repo_gate'] = state.repo_gate
    authoritative_steps['target_gate'] = state.target_gate
    authoritative_steps['hil'] = state.hil_gate
    authoritative_steps['release_checklist'] = state.release_checklist_gate
    authoritative_steps['release_gate'] = state.release_gate
    blocking_steps = {name: status for name, status in authoritative_steps.items() if status in {'failed', 'blocked'}}
    return {
        'environment': env_report,
        'steps': authoritative_steps,
        'allPassed': state.release_gate == 'passed',
        'hasBlockingStep': bool(blocking_steps),
        'blockingSteps': blocking_steps,
        'repoGate': state.repo_gate,
        'targetGate': state.target_gate,
        'hilGate': state.hil_gate,
        'releaseChecklistGate': state.release_checklist_gate,
        'releaseGate': state.release_gate,
        'targetRuntimeReadiness': state.target_gate,
        'negativePathCoverage': {
            'automaticSubset': authoritative_steps.get('negative_path_subset', 'not_executed'),
            'hil': state.hil_gate,
        },
        'evidenceLevels': {
            'L1_static_analysis': 'passed' if authoritative_steps else 'not_executed',
            'L2_repo_tests': state.repo_gate,
            'L3_target_env': state.target_gate,
            'L4_hil': state.hil_gate,
        },
        'evidencePath': evidence_path,
    }
