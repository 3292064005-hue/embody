from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_SRC = ROOT / "backend" / "embodied_arm_ws" / "src"

# Add repository root so the gateway package is importable when pytest runs from the root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Each ROS2-style Python package lives one level below backend/embodied_arm_ws/src/<pkg>/<pkg>.
# Add every immediate package directory so tests can import them without requiring colcon install.
if BACKEND_SRC.exists():
    for child in sorted(BACKEND_SRC.iterdir()):
        if child.is_dir() and (child / child.name).exists():
            path = str(child)
            if path not in sys.path:
                sys.path.insert(0, path)


def pytest_configure(config):
    config.addinivalue_line('markers', 'asyncio: run async test functions with asyncio')


def pytest_pyfunc_call(pyfuncitem):
    if pyfuncitem.get_closest_marker('asyncio') is None:
        return None
    testfunction = pyfuncitem.obj
    if not inspect.iscoroutinefunction(testfunction):
        return None
    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(testfunction(**kwargs))
    return True
