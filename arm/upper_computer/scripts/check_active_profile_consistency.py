from __future__ import annotations

import ast
import configparser
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend' / 'embodied_arm_ws'
PYTEST_ACTIVE = BACKEND / 'pytest-active.ini'
ACTIVE_PROFILE_QUARANTINE = BACKEND / 'active_profile_quarantine.json'
LAUNCH_FACTORY = BACKEND / 'src' / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
def _parse_pythonpath() -> set[str]:
    parser = configparser.ConfigParser()
    parser.read(PYTEST_ACTIVE, encoding='utf-8')
    raw = parser.get('pytest', 'pythonpath', fallback='')
    return {
        line.strip().split('/')[-1]
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith('..')
    }


def _literal_assignment(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise KeyError(name)




def load_launch_package_taxonomy() -> tuple[set[str], set[str], set[str], set[str]]:
    tree = ast.parse(LAUNCH_FACTORY.read_text(encoding='utf-8'))
    core = set(_literal_assignment(tree, 'RUNTIME_CORE_PACKAGES'))
    supervision = set(_literal_assignment(tree, 'RUNTIME_SUPERVISION_PACKAGES'))
    compat = set(_literal_assignment(tree, 'COMPATIBILITY_PACKAGES'))
    experimental = set(_literal_assignment(tree, 'EXPERIMENTAL_PACKAGES'))
    return core, supervision, compat, experimental


def load_launch_workspace_support_packages() -> set[str]:
    tree = ast.parse(LAUNCH_FACTORY.read_text(encoding='utf-8'))
    try:
        return set(_literal_assignment(tree, 'RUNTIME_SUPPORT_PACKAGES'))
    except KeyError:
        return set()


def _parse_launch_packages() -> tuple[set[str], set[str], set[str], set[str]]:
    return load_launch_package_taxonomy()


RUNTIME_CORE_PACKAGES, RUNTIME_SUPERVISION_PACKAGES, DEPRECATED_PACKAGES, EXPERIMENTAL_PACKAGES = load_launch_package_taxonomy()
RUNTIME_SUPPORT_PACKAGES = load_launch_workspace_support_packages()


def _ignored_tests() -> set[str]:
    parser = configparser.ConfigParser()
    parser.read(PYTEST_ACTIVE, encoding='utf-8')
    raw = parser.get('pytest', 'addopts', fallback='')
    ignored = set()
    for token in raw.split():
        if token.startswith('--ignore='):
            ignored.add(token.split('=', 1)[1].split('/')[-1])
    return ignored


def _load_quarantine_manifest() -> list[dict[str, str]]:
    payload = json.loads(ACTIVE_PROFILE_QUARANTINE.read_text(encoding='utf-8')) if ACTIVE_PROFILE_QUARANTINE.exists() else {}
    entries = payload.get('ignoredTests', []) if isinstance(payload, dict) else []
    return [entry for entry in entries if isinstance(entry, dict)]


def _validate_quarantine_manifest() -> list[str]:
    issues: list[str] = []
    entries = _load_quarantine_manifest()
    manifest_names = set()
    ignored = _ignored_tests()
    for entry in entries:
        path = str(entry.get('path', '') or '').strip()
        name = path.split('/')[-1]
        manifest_names.add(name)
        if not path.startswith('tests/'):
            issues.append(f'quarantine entry must target tests/*: {path or entry!r}')
        if not (BACKEND / path).exists():
            issues.append(f'quarantine entry points to missing test file: {path}')
        for field in ('owner', 'category', 'reason', 'expires'):
            if not str(entry.get(field, '') or '').strip():
                issues.append(f'quarantine entry missing {field}: {path or entry!r}')
        expires = str(entry.get('expires', '') or '').strip()
        if expires:
            try:
                expiry = date.fromisoformat(expires)
            except ValueError:
                issues.append(f'quarantine entry has invalid expires date: {path or entry!r}')
            else:
                if expiry < date.today():
                    issues.append(f'quarantine entry expired and must be removed: {path}')
    missing_from_manifest = sorted(ignored - manifest_names)
    missing_from_pytest = sorted(manifest_names - ignored)
    for name in missing_from_manifest:
        issues.append(f'pytest-active.ini ignores {name} but active_profile_quarantine.json does not track it')
    for name in missing_from_pytest:
        issues.append(f'active_profile_quarantine.json tracks {name} but pytest-active.ini does not ignore it')
    return issues


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split('.')[0])
    return imports


def validate_active_profile() -> list[str]:
    issues: list[str] = []
    issues.extend(_validate_quarantine_manifest())
    pythonpath = _parse_pythonpath()
    core, supervision, compat, experimental = _parse_launch_packages()
    expected = core | supervision

    for pkg in sorted(pkg for pkg in expected if pkg not in pythonpath):
        issues.append(f'active pytest pythonpath missing runtime package: {pkg}')
    for pkg in sorted(pkg for pkg in pythonpath if pkg in compat | experimental):
        issues.append(f'active pytest pythonpath includes non-active package: {pkg}')

    ignored = _ignored_tests()
    for test_path in sorted((BACKEND / 'tests').glob('test_*.py')):
        if test_path.name in ignored:
            continue
        for pkg in _top_level_imports(test_path):
            if pkg in DEPRECATED_PACKAGES | EXPERIMENTAL_PACKAGES:
                issues.append(f'active test imports non-active package {pkg}: {test_path.name}')
            if pkg in expected and pkg not in pythonpath:
                issues.append(f'active test imports {pkg} but pytest-active.ini does not expose it: {test_path.name}')
    return issues


def main() -> int:
    issues = validate_active_profile()
    if issues:
        print('ACTIVE PROFILE CONSISTENCY FAILED')
        for issue in issues:
            print(f'- {issue}')
        return 1
    print('ACTIVE PROFILE CONSISTENCY PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
