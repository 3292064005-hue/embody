from __future__ import annotations

"""Materialize frontend validation evidence in JSON and markdown form."""

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts'
REPO_VALIDATION = ARTIFACTS / 'repository_validation'
LEDGER_PATH = ARTIFACTS / 'release_gates' / 'frontend_validation_ledger.json'
DOC_PATH = ROOT / 'docs' / 'evidence' / 'frontend-validation-status.md'
PACKAGE_JSON = ROOT / 'frontend' / 'package.json'

FRONTEND_STEPS: tuple[tuple[str, str, str, bool], ...] = (
    ('frontend-deps', 'dependency install (npm ci)', 'dependencies', True),
    ('frontend-typecheck-app', 'application typecheck', 'typecheck', True),
    ('frontend-typecheck-test', 'test-only typecheck', 'typecheck', True),
    ('frontend-unit', 'unit tests', 'tests', True),
    ('frontend-build', 'frontend build', 'build', True),
    ('frontend-e2e', 'playwright e2e', 'tests', True),
)
PROFILE_PRIORITY = {'release_gates': 5, 'release': 4, 'frontend_manual': 3, 'repo': 2, 'fast': 1}


def _packaged_summary_path() -> Path:
    return ARTIFACTS / 'release_gates' / 'frontend_validation_artifacts' / 'verification_summary.json'


def _stable_generated_at(path: Path | None, payload: dict[str, Any] | None = None) -> str:
    """Return one archive-stable generatedAt token for evidence rendering.

    The ledger must remain stable after split-release packaging and unzip. Using
    filesystem mtimes is unsafe because zip extraction normalizes timestamp
    precision. Prefer one canonical timestamp carried inside the summary payload;
    otherwise fail closed to ``not_available`` instead of inventing a new value.
    """
    if isinstance(payload, dict):
        generated_at = str(payload.get('generatedAt', '') or '').strip()
        if generated_at:
            return generated_at
    if path is None or not path.exists():
        return 'not_available'
    return 'not_available'


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _candidate_profile(path: Path, payload: dict[str, Any]) -> str:
    if path == _packaged_summary_path():
        profile = str(payload.get('profile', '') or '').strip()
        return profile or 'release_gates'
    profile = str(payload.get('profile', '') or '').strip()
    return profile or path.parent.name


def _detect_build_profile(summary_path: Path | None, logs: dict[str, Any]) -> str:
    if summary_path is None:
        return ''
    log_name = str(logs.get('frontend-build', 'frontend-build.log') or 'frontend-build.log').strip()
    build_log = summary_path.parent / log_name
    if not build_log.exists():
        return ''
    text = build_log.read_text(encoding='utf-8', errors='replace').lower()
    match = re.search(r'buildprofile=([a-z0-9_-]+)', text)
    return match.group(1) if match else ''


def _best_summary() -> tuple[Path | None, dict[str, Any]]:
    candidates: list[tuple[int, int, float, Path, dict[str, Any]]] = []
    candidate_paths = list(REPO_VALIDATION.glob('*/verification_summary.json'))
    packaged_summary = _packaged_summary_path()
    if packaged_summary.exists() and not candidate_paths:
        candidate_paths.append(packaged_summary)
    for path in candidate_paths:
        payload = _load_json(path)
        profile = _candidate_profile(path, payload)
        step_statuses = payload.get('stepStatuses', {}) if isinstance(payload.get('stepStatuses'), dict) else {}
        executed_frontend_steps = sum(
            1
            for step, *_ in FRONTEND_STEPS
            if str(step_statuses.get(step, 'not_executed') or 'not_executed') in {'passed', 'failed', 'blocked', 'skipped'}
        )
        candidates.append((PROFILE_PRIORITY.get(profile, 0), executed_frontend_steps, path.stat().st_mtime if path.exists() else 0.0, path, payload))
    if not candidates:
        return None, {}
    _, _, _, chosen, payload = sorted(candidates, key=lambda item: (item[0], item[1], item[2]), reverse=True)[0]
    return chosen, payload


def build_frontend_validation_ledger() -> dict[str, Any]:
    summary_path, summary = _best_summary()
    step_statuses = summary.get('stepStatuses', {}) if isinstance(summary.get('stepStatuses'), dict) else {}
    logs = summary.get('logs', {}) if isinstance(summary.get('logs'), dict) else {}
    overall_status = 'not_executed'
    matrix: list[dict[str, Any]] = []
    source_profile = _candidate_profile(summary_path, summary) if summary_path is not None else ''
    if summary_path is None:
        source_summary_rel = ''
    else:
        try:
            source_summary_rel = summary_path.relative_to(ROOT).as_posix()
        except ValueError:
            source_summary_rel = str(summary_path)

    build_profile = _detect_build_profile(summary_path, logs)
    for step, label, group, required in FRONTEND_STEPS:
        status = str(step_statuses.get(step, 'not_executed') or 'not_executed')
        if status not in {'passed', 'failed', 'blocked', 'skipped', 'not_executed'}:
            status = 'not_executed'
        effective_label = label
        if step == 'frontend-build':
            if build_profile in {'release', 'production'}:
                effective_label = 'release build'
            elif build_profile:
                effective_label = f'frontend build ({build_profile} profile)'
                if status == 'passed' and source_profile in {'release_gates', 'release'}:
                    status = 'blocked'
            else:
                effective_label = 'frontend build (profile unknown)'
                if status == 'passed' and source_profile in {'release_gates', 'release'}:
                    status = 'blocked'
        log_name = str(logs.get(step, f'{step}.log') or f'{step}.log').strip()
        log_path = ''
        exists = False
        blocking_class = 'none'
        if summary_path is not None:
            candidate = summary_path.parent / log_name
            log_path = candidate.relative_to(ROOT).as_posix()
            exists = candidate.exists()
            if step == 'frontend-e2e' and exists:
                try:
                    log_text = candidate.read_text(encoding='utf-8', errors='replace').lower()
                except Exception:
                    log_text = ''
                if status == 'skipped' and 'no usable chromium executable is available' in log_text:
                    blocking_class = 'infrastructure'
                elif status in {'failed', 'blocked'}:
                    blocking_class = 'product_or_test'
            elif step == 'frontend-build' and status == 'blocked':
                blocking_class = 'product_or_test'
        matrix.append(
            {
                'step': step,
                'label': effective_label,
                'group': group,
                'required': required,
                'status': status,
                'blockingClass': blocking_class,
                'logPath': log_path,
                'logExists': exists,
            }
        )

    statuses = [item['status'] for item in matrix]
    if any(status == 'failed' for status in statuses):
        overall_status = 'failed'
    elif any(status in {'blocked', 'skipped'} for status in statuses):
        overall_status = 'blocked'
    elif statuses and all(status == 'passed' for status in statuses):
        overall_status = 'passed'
    elif any(status == 'passed' for status in statuses):
        overall_status = 'partial'

    package_payload = _load_json(PACKAGE_JSON)
    engines = package_payload.get('engines', {}) if isinstance(package_payload.get('engines'), dict) else {}
    return {
        'schemaVersion': 1,
        'generatedAt': _stable_generated_at(summary_path, summary),
        'sourceProfile': source_profile,
        'sourceSummary': source_summary_rel,
        'overallStatus': overall_status,
        'environment': {
            'node': str(engines.get('node', '') or ''),
            'packageManager': str(package_payload.get('packageManager', '') or ''),
            'playwrightBrowserContract': 'chromium preinstalled via CI or PLAYWRIGHT_CHROMIUM_EXECUTABLE',
            'environmentReady': not any(item['blockingClass'] == 'infrastructure' for item in matrix),
            'buildProfile': build_profile or 'unknown',
        },
        'matrix': matrix,
    }


def build_frontend_validation_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        '# Frontend Validation Status',
        '',
        '> Status: evidence',
        '> Canonical verification rules: `../operations/verification-and-release.md`',
        f"> Machine-readable ledger: `../../artifacts/release_gates/frontend_validation_ledger.json`",
        '',
        '本文件只记录最近一次可审计的前端验证矩阵与产物位置；规则、门槛与命令仍以 canonical verification 文档为准。若走手工前端验证路径，必须先执行 `python scripts/verify_frontend_validation.py` 生成 auditable summary，再运行本脚本。',
        '',
        f"- overall status: `{str(ledger.get('overallStatus', 'not_executed') or 'not_executed')}`",
        f"- source profile: `{str(ledger.get('sourceProfile', '') or 'unknown')}`",
        f"- source summary: `{str(ledger.get('sourceSummary', '') or 'artifacts/repository_validation/*/verification_summary.json')}`",
        f"- generated at: `{str(ledger.get('generatedAt', '') or '')}`",
        '',
        '## Environment contract snapshot',
        f"- Node.js: `{str(((ledger.get('environment') or {}).get('node', '')) or 'unknown')}`",
        f"- package manager: `{str(((ledger.get('environment') or {}).get('packageManager', '')) or 'unknown')}`",
        '',
        '## Validation matrix',
        '',
        '| Step | Group | Status | Required | Blocking Class | Log |',
        '|---|---|---|---|---|---|',
    ]
    for item in ledger.get('matrix', []):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {str(item.get('label', item.get('step', '')) or '')} | "
            f"{str(item.get('group', '') or '')} | "
            f"`{str(item.get('status', 'not_executed') or 'not_executed')}` | "
            f"{'yes' if bool(item.get('required', True)) else 'no'} | "
            f"`{str(item.get('blockingClass', 'none') or 'none')}` | "
            f"`{str(item.get('logPath', '-') or '-')}` |"
        )
    lines.extend(
        [
            '',
            '## Interpretation',
            '- `passed`: 该步骤已在当前 evidence 来源中成功完成。',
            '- `failed`: 该步骤在 evidence 来源中失败；需要查看对应 log。',
            '- `skipped`: 该步骤由于环境前置条件缺失而被显式跳过，不能视为通过。',
            '- `blocked`: 整体状态使用；表示存在跳过/阻塞步骤，验证链必须 fail-closed。',
            '- `not_executed`: 当前仓库内没有可审计的最近一次执行记录。',
            '- `partial`: 仅整体状态会使用；表示矩阵中存在已执行与未执行混合情况。',
            '',
            '## Maintenance rule',
            '- 该 evidence 文件与 JSON ledger 由脚本生成，不应手工编辑。',
            '- 当 repository validation lane 的前端步骤、日志布局或命名变化时，需同步更新生成脚本。',
            '',
        ]
    )
    return '\n'.join(lines)


def build_packaged_frontend_summary(ledger: dict[str, Any], source_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one canonical packaged verification summary that matches the ledger.

    The packaged ``verification_summary.json`` must not preserve pre-normalized
    statuses that the ledger has already fail-closed. Otherwise downstream
    consumers would see two authoritative answers for the same frontend lane.
    """
    source = source_summary if isinstance(source_summary, dict) else {}
    source_logs = source.get('logs', {}) if isinstance(source.get('logs'), dict) else {}
    matrix = ledger.get('matrix', []) if isinstance(ledger.get('matrix'), list) else []
    step_statuses: dict[str, str] = {}
    logs: dict[str, str] = {}
    required_steps: list[str] = []
    for step, *_ in FRONTEND_STEPS:
        required_steps.append(step)
        entry = next((item for item in matrix if isinstance(item, dict) and str(item.get('step', '') or '') == step), None)
        status = str((entry or {}).get('status', 'not_executed') or 'not_executed')
        if status not in {'passed', 'failed', 'blocked', 'skipped', 'not_executed'}:
            status = 'not_executed'
        step_statuses[step] = status
        log_path = str((entry or {}).get('logPath', '') or '').strip()
        log_name = Path(log_path).name if log_path else str(source_logs.get(step, f'{step}.log') or f'{step}.log')
        logs[step] = log_name
    return {
        'profile': str(ledger.get('sourceProfile', '') or source.get('profile', '') or 'release_gates'),
        'generatedAt': str(ledger.get('generatedAt', '') or source.get('generatedAt', '') or 'not_available'),
        'generatedBy': 'scripts/write_frontend_validation_status.py',
        'normalizedFromSourceSummary': str(ledger.get('sourceSummary', '') or ''),
        'overallStatus': str(ledger.get('overallStatus', 'not_executed') or 'not_executed'),
        'requiredSteps': required_steps,
        'stepStatuses': step_statuses,
        'logs': logs,
        'buildProfile': str(((ledger.get('environment') or {}).get('buildProfile', 'unknown')) or 'unknown'),
    }


def render_outputs() -> dict[Path, str]:
    _, source_summary = _best_summary()
    ledger = build_frontend_validation_ledger()
    packaged_summary = build_packaged_frontend_summary(ledger, source_summary)
    return {
        _packaged_summary_path(): json.dumps(packaged_summary, ensure_ascii=False, indent=2) + '\n',
        LEDGER_PATH: json.dumps(ledger, ensure_ascii=False, indent=2) + '\n',
        DOC_PATH: build_frontend_validation_markdown(ledger) + '\n',
    }


def check_outputs() -> list[str]:
    issues: list[str] = []
    for path, expected in render_outputs().items():
        if not path.exists():
            issues.append(f'missing frontend validation artifact: {path.relative_to(ROOT).as_posix()}')
            continue
        if path.read_text(encoding='utf-8') != expected:
            issues.append(f'frontend validation artifact drift: {path.relative_to(ROOT).as_posix()}')
    return issues


def write_outputs() -> None:
    for path, content in render_outputs().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate or verify frontend validation evidence artifacts.')
    parser.add_argument('--check', action='store_true', help='Fail if the evidence markdown or JSON ledger are stale.')
    args = parser.parse_args()
    if args.check:
        issues = check_outputs()
        if issues:
            raise SystemExit('\n'.join(issues))
        print('frontend validation evidence is in sync')
        return 0
    write_outputs()
    print('frontend validation evidence updated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
