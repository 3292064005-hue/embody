from __future__ import annotations

import ast
from pathlib import Path

from check_active_profile_consistency import load_launch_package_taxonomy

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend' / 'embodied_arm_ws'
GATEWAY = ROOT / 'gateway'


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


def _iter_python_files() -> list[Path]:
    core, supervision, _, _ = load_launch_package_taxonomy()
    package_roots = [BACKEND / 'tests', GATEWAY]
    for package_name in sorted(core | supervision):
        package_roots.append(BACKEND / 'src' / package_name)
    paths: list[Path] = []
    for root in package_roots:
        if not root.exists():
            continue
        paths.extend(sorted(path for path in root.rglob('*.py') if '__pycache__' not in path.parts))
    return paths


def validate_deprecated_runtime_usage() -> list[str]:
    _, _, deprecated, experimental = load_launch_package_taxonomy()
    disallowed = deprecated | experimental
    issues: list[str] = []
    for path in _iter_python_files():
        for imported in sorted(_top_level_imports(path)):
            if imported in disallowed:
                issues.append(f'disallowed deprecated/experimental import {imported} in {path.relative_to(ROOT)}')
    return issues


def main() -> int:
    issues = validate_deprecated_runtime_usage()
    if issues:
        print('DEPRECATED RUNTIME USAGE CHECK FAILED')
        for issue in issues:
            print(f'- {issue}')
        return 1
    print('DEPRECATED RUNTIME USAGE CHECK PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
