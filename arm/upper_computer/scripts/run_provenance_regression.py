#!/usr/bin/env python3
from __future__ import annotations

"""Run release provenance regression tests without external pytest.

This runner is the zero-dependency release gate for the provenance tests in
`tests/test_release_manifest_provenance.py`. It executes every `test_*`
function in that module and supplies a temporary `tmp_path` when the test
function declares it.
"""

import argparse
import inspect
import importlib.util
import sys
import tempfile
import traceback
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
TEST_PATH = ROOT / 'tests' / 'test_release_manifest_provenance.py'


def _load_test_module(path: Path) -> ModuleType:
    """Load the provenance test module by path.

    Args:
        path: Python test module path.

    Returns:
        Loaded module object.

    Raises:
        RuntimeError: If importlib cannot construct a loader for the file.
    """
    spec = importlib.util.spec_from_file_location('provenance_regression_tests', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'failed to load provenance tests: {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_test(name: str, func: object) -> tuple[bool, str]:
    """Run one test function with stdlib fixture substitution.

    Args:
        name: Test function name.
        func: Callable test object.

    Returns:
        `(passed, detail)` tuple. `detail` is empty for passes and contains the
        traceback for failures.

    Boundary behavior:
        Only the `tmp_path` fixture is supplied because this provenance suite is
        deliberately kept pytest-independent. Unknown required parameters fail
        closed so new tests cannot silently be skipped.
    """
    if not callable(func):
        return True, ''
    signature = inspect.signature(func)
    parameters = list(signature.parameters.values())
    kwargs: dict[str, object] = {}
    unknown = [p.name for p in parameters if p.default is inspect._empty and p.name != 'tmp_path']
    if unknown:
        return False, f'unsupported required fixture(s): {unknown}'
    try:
        if any(p.name == 'tmp_path' for p in parameters):
            with tempfile.TemporaryDirectory(prefix=f'{name}_') as temp_dir:
                kwargs['tmp_path'] = Path(temp_dir)
                func(**kwargs)
        else:
            func()
    except Exception:
        return False, traceback.format_exc()
    return True, ''


def run() -> int:
    """Execute all provenance regression tests and return a process exit code."""
    module = _load_test_module(TEST_PATH)
    tests = sorted(
        (name, getattr(module, name))
        for name in dir(module)
        if name.startswith('test_') and callable(getattr(module, name))
    )
    failures: list[tuple[str, str]] = []
    for name, func in tests:
        passed, detail = _run_test(name, func)
        if passed:
            print(f'[provenance-regression] PASS {name}')
        else:
            print(f'[provenance-regression] FAIL {name}')
            failures.append((name, detail))
    if failures:
        print(f'[provenance-regression] {len(failures)}/{len(tests)} failed')
        for name, detail in failures:
            print(f'\n--- {name} ---\n{detail}')
        return 1
    print(f'[provenance-regression] {len(tests)}/{len(tests)} passed')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    return run()


if __name__ == '__main__':
    raise SystemExit(main())
