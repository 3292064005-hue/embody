from __future__ import annotations

import ast
import configparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend' / 'embodied_arm_ws'
PYTEST_ACTIVE = BACKEND / 'pytest-active.ini'
LAUNCH_FACTORY = BACKEND / 'src' / 'arm_bringup' / 'arm_bringup' / 'launch_factory.py'
DEPRECATED_PACKAGES = {'arm_task_manager', 'arm_motion_bridge'}
EXPERIMENTAL_PACKAGES = {'arm_hmi', 'arm_esp32_gateway'}


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


def _parse_launch_packages() -> tuple[set[str], set[str], set[str], set[str]]:
    tree = ast.parse(LAUNCH_FACTORY.read_text(encoding='utf-8'))
    core = set(_literal_assignment(tree, 'RUNTIME_CORE_PACKAGES'))
    supervision = set(_literal_assignment(tree, 'RUNTIME_SUPERVISION_PACKAGES'))
    compat = set(_literal_assignment(tree, 'COMPATIBILITY_PACKAGES'))
    experimental = set(_literal_assignment(tree, 'EXPERIMENTAL_PACKAGES'))
    return core, supervision, compat, experimental


def _ignored_tests() -> set[str]:
    parser = configparser.ConfigParser()
    parser.read(PYTEST_ACTIVE, encoding='utf-8')
    raw = parser.get('pytest', 'addopts', fallback='')
    ignored = set()
    for token in raw.split():
        if token.startswith('--ignore='):
            ignored.add(token.split('=', 1)[1].split('/')[-1])
    return ignored


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
